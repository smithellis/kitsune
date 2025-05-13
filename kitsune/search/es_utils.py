import importlib
import inspect

from celery import shared_task
from django.conf import settings
from elasticsearch import Elasticsearch
from elasticsearch.helpers.errors import BulkIndexError
from elasticsearch_dsl import Document, UpdateByQuery, analyzer, char_filter, token_filter

from kitsune.search import config


def _insert_custom_filters(analyzer_name, filter_list, char=False):
    """
    Takes a list containing in-built filters (as strings), and the settings for custom filters
    (as dicts). Turns the dicts into instances of `token_filter` or `char_filter` depending
    on the value of the `char` argument.
    """

    def mapping_func(position_filter_tuple):
        position, filter = position_filter_tuple
        if type(filter) is dict:
            prefix = analyzer_name
            default_filters = config.ES_DEFAULT_ANALYZER["char_filter" if char else "filter"]
            if filter in default_filters:
                # detect if this filter exists in the default analyzer
                # if it does use the same name as the default
                # to avoid defining the same filter for each locale
                prefix = config.ES_DEFAULT_ANALYZER_NAME
                position = default_filters.index(filter)
            name = f'{prefix}_{position}_{filter["type"]}'
            if char:
                return char_filter(name, **filter)
            return token_filter(name, **filter)
        return filter

    return list(map(mapping_func, enumerate(filter_list)))


def _create_synonym_graph_filter(synonym_file_name):
    filter_name = f"{synonym_file_name}_synonym_graph"
    return token_filter(
        filter_name,
        type="synonym_graph",
        synonyms_path=f"synonyms/{synonym_file_name}.txt",
        expand="true",
        lenient="true",
        updateable="true",
    )


def es_analyzer_for_locale(locale, search_analyzer=False):
    """Pick an appropriate analyzer for a given locale.
    If no analyzer is defined for `locale` or the locale analyzer uses a plugin
    but using plugin is turned off from settings, return an analyzer named "default_sumo".
    """

    name = ""
    analyzer_config = config.ES_LOCALE_ANALYZERS.get(locale)

    if not analyzer_config or (analyzer_config.get("plugin") and not settings.ES_USE_PLUGINS):
        name = config.ES_DEFAULT_ANALYZER_NAME
        analyzer_config = {}

    # use default values from ES_DEFAULT_ANALYZER if not overridden
    # using python 3.9's dict union operator
    analyzer_config = config.ES_DEFAULT_ANALYZER | analyzer_config

    # turn dictionaries into `char_filter` and `token_filter` instances
    filters = _insert_custom_filters(name or locale, analyzer_config["filter"])
    char_filters = _insert_custom_filters(
        name or locale, analyzer_config["char_filter"], char=True
    )

    if search_analyzer:
        # create a locale-specific search analyzer, even if the index-time analyzer is
        # `sumo_default`. we do this so that we can adjust the synonyms used in any locale,
        # even if it doesn't have a custom analysis chain set up, without having to re-index
        name = locale + "_search_analyzer"
        filters.append(_create_synonym_graph_filter(config.ES_ALL_SYNONYMS_NAME))
        filters.append(_create_synonym_graph_filter(locale))

    return analyzer(
        name or locale,
        tokenizer=analyzer_config["tokenizer"],
        filter=filters,
        char_filter=char_filters,
    )


def es_client(**kwargs):
    """Return an ES Elasticsearch client"""
    # prefer a cloud_id if available
    if es_cloud_id := settings.ES_CLOUD_ID:
        kwargs.update({"cloud_id": es_cloud_id, "basic_auth": settings.ES_HTTP_AUTH})
    else:
        # Basic ES settings that apply to all versions
        es_settings = {
            "hosts": settings.ES_URLS,
        }

        # Add settings that are specific to ES 8+
        if getattr(settings, "ES_VERSION", 0) >= 8:
            es_settings.update(
                {
                    "request_timeout": settings.ES_TIMEOUT,
                    "retry_on_timeout": settings.ES_RETRY_ON_TIMEOUT,
                    # SSL settings - these are needed for ES8 which requires SSL by default
                    "verify_certs": settings.ES_VERIFY_CERTS,
                    "ssl_show_warn": settings.ES_SSL_SHOW_WARN,
                }
            )

        if settings.ES_HTTP_AUTH:
            es_settings.update({"basic_auth": settings.ES_HTTP_AUTH})

        kwargs.update(es_settings)

    return Elasticsearch(**kwargs)


def get_doc_types(paths=["kitsune.search.documents"]):
    """Return all registered document types"""

    doc_types = []
    modules = [importlib.import_module(path) for path in paths]

    for module in modules:
        for key in dir(module):
            cls = getattr(module, key)
            if (
                inspect.isclass(cls)
                and issubclass(cls, Document)
                and cls != Document
                and cls.__name__ != "SumoDocument"
            ):
                doc_types.append(cls)
    return doc_types


@shared_task
def index_object(doc_type_name, obj_id):
    """
    Index an object in the search index.

    Args:
        doc_type_name: Name of the document type
        obj_id: ID of the object to index
    """
    doc_type = next(cls for cls in get_doc_types() if cls.__name__ == doc_type_name)

    try:
        obj = model = doc_type.get_model()
        if isinstance(obj_id, model):
            obj = obj_id
        else:
            obj = model.objects.get(pk=obj_id)
    except model.DoesNotExist:
        # if the row doesn't exist in DB, it may have been deleted while this job
        # was in the celery queue - this shouldn't be treated as a failure, so
        # just return
        return

    # Prepare the document
    prepared_doc = doc_type.prepare(obj)

    # Set refresh parameter based on ES version and test mode
    refresh = None
    if settings.TEST:
        refresh = "true" if getattr(settings, "ES_VERSION", 0) >= 8 else True

    # Use appropriate indexing approach based on document update setting and ES version
    try:
        es_version = getattr(settings, "ES_VERSION", 7)
        if doc_type.update_document:
            if es_version >= 8:
                # For ES8+, use regular save without doc_as_upsert
                prepared_doc.save(refresh=refresh)
            else:
                # For ES7 and below, don't pass script parameter
                # The ES7 client doesn't accept script=None
                prepared_doc.save(refresh=refresh)
        else:
            # For non-update documents, use regular save
            prepared_doc.save(refresh=refresh)
    except Exception:
        print(f"Error indexing {doc_type_name} {obj_id}")
        raise


@shared_task
def index_objects_bulk(
    doc_type_name,
    obj_ids,
    timeout=settings.ES_BULK_DEFAULT_TIMEOUT,
    elastic_chunk_size=settings.ES_DEFAULT_ELASTIC_CHUNK_SIZE,
):
    """Bulk index ORM objects given a list of object ids and a document type name."""
    doc_type = next(cls for cls in get_doc_types() if cls.__name__ == doc_type_name)
    db_objects = doc_type.get_queryset().filter(pk__in=obj_ids)

    # Get the client with appropriate timeout settings
    client = es_client(
        request_timeout=timeout,
        retry_on_timeout=True,
    )

    # Count of successfully indexed documents
    success_count = 0
    error_count = 0
    errors = []

    # Process in chunks to avoid memory issues
    for i in range(0, len(db_objects), elastic_chunk_size):
        chunk = db_objects[i : i + elastic_chunk_size]
        docs = []

        # Prepare all documents in the chunk
        for obj in chunk:
            try:
                prepared = doc_type.prepare(obj)
                docs.append(prepared)
            except Exception as e:
                errors.append({"id": obj.pk, "error": str(e), "type": "preparation_error"})
                error_count += 1

        # Index all prepared documents in the chunk
        for doc in docs:
            try:
                # Set refresh parameter based on ES version and test mode
                refresh = None
                if settings.TEST:
                    refresh = "true" if getattr(settings, "ES_VERSION", 0) >= 8 else True

                # Use appropriate indexing approach based on document update setting and ES version
                es_version = getattr(settings, "ES_VERSION", 7)
                if doc_type.update_document:
                    if es_version >= 8:
                        # For ES8+, use regular save without doc_as_upsert
                        doc.save(refresh=refresh)
                    else:
                        # For ES7 and below, don't pass script parameter
                        doc.save(refresh=refresh)
                else:
                    # For non-update documents, use regular save
                    doc.save(refresh=refresh)

                success_count += 1
            except Exception:
                errors.append(
                    {
                        "id": getattr(doc.meta, "id", "unknown"),
                        "error": "Error indexing document",
                        "type": "indexing_error",
                    }
                )
                error_count += 1

    # Refresh the index to make documents searchable immediately
    if not settings.TEST:  # Only if not already refreshed in test mode
        try:
            client.indices.refresh(index=doc_type._index._name)
        except Exception:
            # Log but don't fail on refresh error
            print("Warning: Index refresh failed")

    # Report errors if any occurred
    if errors:
        raise BulkIndexError(f"{error_count} document(s) failed to index.", errors)

    return success_count


@shared_task
def remove_from_field(doc_type_name, field_name, field_value):
    """
    Given a document type name, a field name, and a value, looks up all
    documents containing that value in the specified field and removes
    the value from the field (if it's a list field).
    """
    doc_type = next(cls for cls in get_doc_types() if cls.__name__ == doc_type_name)

    # Create script as a string
    if getattr(settings, "ES_VERSION", 0) >= 8:
        script_source = (
            f"if (ctx._source.{field_name} != null) {{ "
            f"ctx._source.{field_name}.removeAll(Collections.singleton(params.value)); "
            f"}}"
        )
    else:
        script_source = (
            f"if (ctx._source.{field_name}.contains(params.value)) {{"
            f"ctx._source.{field_name}.remove(ctx._source.{field_name}.indexOf(params.value))"
            f"}}"
        )

    # Set up the update query
    update = UpdateByQuery(using=es_client(), index=doc_type._index._name)

    # Apply the script with parameters
    if getattr(settings, "ES_VERSION", 0) >= 8:
        update = update.script(
            source=script_source, lang="painless", params={"value": field_value}
        )
    else:
        # For ES7 and below, we need to filter documents explicitly
        update = update.filter("term", **{field_name: field_value})
        update = update.script(
            source=script_source,
            lang="painless",
            params={"value": field_value},
            conflicts="proceed",
        )

    # refresh index to ensure search fetches all matches
    doc_type._index.refresh()

    update.execute()


@shared_task
def delete_object(doc_type_name, obj_id):
    """
    Delete an object from the search index.

    Args:
        doc_type_name: Name of the document type
        obj_id: ID of the object to delete
    """
    doc_type = next(cls for cls in get_doc_types() if cls.__name__ == doc_type_name)

    # Set refresh parameter based on ES version
    refresh = None
    if settings.TEST:
        refresh = "true" if getattr(settings, "ES_VERSION", 0) >= 8 else True

    try:
        # Create a document with just the ID and delete it
        doc = doc_type(meta={"id": obj_id})
        doc.delete(refresh=refresh, ignore=404)  # Ignore 404 errors if document is not found

        # For test mode, explicitly refresh the index to ensure deletion is visible immediately
        if settings.TEST and not refresh:
            es_client().indices.refresh(index=doc_type._index._name)
    except Exception:
        print(f"Error deleting {doc_type_name} {obj_id}")
        # Don't re-raise the error since deletion failures are usually not critical


def index_objects(doc_type_name, obj_ids, refresh=False):
    """
    Index a list of objects directly (without using Celery).
    This is useful for tests or direct indexing scenarios.

    Args:
        doc_type_name: Name of the document type to index
        obj_ids: List of object IDs to index
        refresh: Whether to refresh the index after indexing

    Returns:
        int: Number of successfully indexed documents
    """
    doc_type = next(cls for cls in get_doc_types() if cls.__name__ == doc_type_name)

    # Get objects from database
    db_objects = doc_type.get_queryset().filter(pk__in=obj_ids)

    # Set refresh parameter based on ES version
    refresh_param = None
    if refresh:
        refresh_param = "true" if getattr(settings, "ES_VERSION", 0) >= 8 else True

    # Index each document
    success_count = 0
    for obj in db_objects:
        try:
            prepared = doc_type.prepare(obj)
            if doc_type.update_document:
                if getattr(settings, "ES_VERSION", 0) >= 8:
                    # For ES8+, use regular save without doc_as_upsert
                    prepared.save(refresh=refresh_param)
                else:
                    # For ES7 and below, use script=None (equivalent to doc_as_upsert=True)
                    prepared.save(refresh=refresh_param, script=None)
            else:
                prepared.save(refresh=refresh_param)
            success_count += 1
        except Exception as e:
            print(f"Error indexing {doc_type_name} {obj.pk}: {str(e)}")

    # Refresh the index if requested
    if refresh and not refresh_param:
        try:
            es_client().indices.refresh(index=doc_type._index._name)
        except Exception as e:
            print(f"Warning: Index refresh failed: {str(e)}")

    return success_count

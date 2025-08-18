import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from dataclasses import field as dfield
from datetime import datetime
from typing import Self, overload

from django.conf import settings
from django.core.paginator import EmptyPage, PageNotAnInteger
from django.core.paginator import Paginator as DjPaginator
from django.utils import timezone
from django.utils.translation import gettext as _
from elasticsearch import NotFoundError, RequestError
from elasticsearch.dsl import Document as DSLDocument
from elasticsearch.dsl import InnerDoc, MetaField, field
from elasticsearch.dsl import Search as DSLSearch
from elasticsearch.dsl.utils import AttrDict
from pyparsing import ParseException

from kitsune.search.config import (
    DEFAULT_ES_CONNECTION,
    DEFAULT_ES_REFRESH_INTERVAL,
    UPDATE_RETRY_ON_CONFLICT,
)
from kitsune.search.es_utils import es_client
from kitsune.search.parser import Parser
from kitsune.search.parser.tokens import TermToken


class SumoDocument(DSLDocument):
    """Base class with common methods for all the different documents."""

    # Controls if a document should be indexed or updated in ES.
    #   True: An update action will be performed in ES.
    #   False: An index action will be performed in ES.
    update_document = False

    indexed_on = field.Date()

    class Meta:
        # ignore fields if they don't exist in the mapping
        dynamic = MetaField("false")

    def __init_subclass__(cls, **kwargs):
        """Automatically set up each subclass' Index attribute."""
        super().__init_subclass__(**kwargs)

        cls.Index.using = DEFAULT_ES_CONNECTION

        # Determine index name based on inheritance hierarchy
        immediate_parent = cls.__mro__[1]
        name = cls.__name__ if immediate_parent is SumoDocument else immediate_parent.__name__

        # Set up index aliases and settings
        cls.Index.base_name = f"{settings.ES_INDEX_PREFIX}_{name.lower()}"
        cls.Index.read_alias = f"{cls.Index.base_name}_read"
        cls.Index.write_alias = f"{cls.Index.base_name}_write"
        cls.Index.settings = {
            "refresh_interval": DEFAULT_ES_REFRESH_INTERVAL,
            "mapping.nested_fields.limit": 1000,
            "mapping.total_fields.limit": 2000,
        }
        cls.Index.name = cls.Index.write_alias

    @classmethod
    def search(cls, **kwargs):
        """Create an elasticsearch_dsl.Search instance for this Document."""
        kwargs.setdefault("index", cls.Index.read_alias)
        return super().search(**kwargs)

    @classmethod
    def migrate_writes(cls, timestamp=None):
        """Create a new index for this document, and point the write alias at it."""
        timestamp = timestamp or datetime.now(tz=timezone.utc)
        name = f"{cls.Index.base_name}_{timestamp.strftime('%Y%m%d%H%M%S')}"
        cls.init(index=name)
        cls._update_alias(cls.Index.write_alias, name)

    @classmethod
    def migrate_reads(cls):
        """Point the read alias at the same index as the write alias."""
        cls._update_alias(cls.Index.read_alias, cls.alias_points_at(cls.Index.write_alias))

    @classmethod
    def _update_alias(cls, alias, new_index):
        client = es_client()
        old_index = cls.alias_points_at(alias)
        if not old_index:
            client.indices.put_alias(index=new_index, name=alias)
        else:
            client.indices.update_aliases(
                actions=[
                    {"remove": {"index": old_index, "alias": alias}},
                    {"add": {"index": new_index, "alias": alias}},
                ]
            )

    @classmethod
    def alias_points_at(cls, alias):
        """Returns the index `alias` points at."""
        try:
            aliased_indices = list(es_client().indices.get_alias(name=alias))
        except NotFoundError:
            return None

        if len(aliased_indices) > 1:
            raise RuntimeError(f"{alias} points at more than one index")

        return aliased_indices[0] if aliased_indices else None

    @classmethod
    def prepare(cls, instance, parent_id=None, **kwargs):
        """Prepare an object given a model instance."""
        obj = cls()

        if hasattr(instance, "es_discard_doc"):
            obj.es_discard_doc = "unindex_me"
        else:
            cls._prepare_fields(obj, instance, parent_id)

        obj.indexed_on = datetime.now(timezone.utc)
        obj.meta.id = parent_id or instance.pk
        return obj

    @classmethod
    def _prepare_fields(cls, obj, instance, parent_id):
        """Process and set field values for the document."""
        doc_mapping = obj._doc_type.mapping
        fields = [f for f in doc_mapping if f != "indexed_on"]

        for field_name in fields:
            cls._prepare_single_field(obj, instance, field_name, doc_mapping, parent_id)

    @classmethod
    def _prepare_single_field(cls, obj, instance, field_name, doc_mapping, parent_id):
        """Prepare a single field value."""
        prepare_method = getattr(obj, f"prepare_{field_name}", None)
        value = obj.get_field_value(field_name, instance, prepare_method)

        field_type = doc_mapping.resolve_field(field_name)

        if cls._is_locale_object_field(field_type, value):
            cls._set_locale_field(obj, instance, field_name, value)
        else:
            cls._set_regular_field(obj, field_name, field_type, value, parent_id)

    @classmethod
    def _is_locale_object_field(cls, field_type, value):
        """Check if field is a locale-aware Object field."""
        if not isinstance(field_type, field.Object):
            return False

        if isinstance(value, InnerDoc):
            return False

        if isinstance(value, list) and value and isinstance(value[0], InnerDoc):
            return False

        return True

    @classmethod
    def _set_locale_field(cls, obj, instance, field_name, value):
        """Set value for locale-aware Object field."""
        locale = obj.prepare_locale(instance)
        if locale and value is not None:
            obj[field_name] = {locale: value}

    @classmethod
    def _set_regular_field(cls, obj, field_name, field_type, value, parent_id):
        """Set value for regular field."""
        if isinstance(field_type, field.Date) and isinstance(value, datetime) and timezone.is_naive(value):
            value = timezone.make_aware(value).astimezone(timezone.utc)

        if not parent_id:
            setattr(obj, field_name, value)

    def to_action(self, action=None, is_bulk=False, **kwargs):
        """Construct data for save, delete, update operations."""
        # Override action for discarded documents
        if hasattr(self, "es_discard_doc"):
            action = "delete"
            kwargs = {}

        payload = self.to_dict(include_meta=is_bulk, skip_empty=False)

        # Set refresh for test environment
        if settings.TEST and not is_bulk:
            kwargs["refresh"] = True

        return self._execute_action(action or "index", payload, is_bulk, kwargs)

    def _execute_action(self, action, payload, is_bulk, kwargs):
        """Execute the specified action."""
        if action == "index":
            return payload if is_bulk else self.save(**kwargs)
        elif action == "update":
            return self._handle_update(payload, is_bulk, kwargs)
        elif action == "delete":
            return self._handle_delete(payload, is_bulk, kwargs)

    def _handle_update(self, payload, is_bulk, kwargs):
        """Handle update action."""
        payload.update(kwargs)

        if is_bulk:
            payload.update({
                "doc": payload["_source"],
                "_op_type": "update",
                "retry_on_conflict": UPDATE_RETRY_ON_CONFLICT,
            })
            del payload["_source"]
            return payload

        return self.update(**payload)

    def _handle_delete(self, payload, is_bulk, kwargs):
        """Handle delete action."""
        if is_bulk:
            payload.update({"_op_type": "delete"})
            del payload["_source"]
            return payload

        kwargs.update({"ignore": [400, 404]})
        return self.delete(**kwargs)

    @classmethod
    def get_queryset(cls):
        """Return the manager for a document's model."""
        return cls.get_model()._default_manager

    def get_field_value(self, field, instance, prepare_method):
        """Get field value using prepare method or direct attribute access."""
        return prepare_method(instance) if prepare_method else getattr(instance, field)

    def prepare_locale(self, instance):
        """Return the locale of an object if it exists."""
        return getattr(instance, 'locale', '') or ''


class SumoSearchInterface(ABC):
    """Base interface for search classes."""

    @abstractmethod
    def get_index(self):
        """The index or comma-separated indices to search over."""
        ...

    @abstractmethod
    def get_fields(self):
        """Fields to search over."""
        ...

    def get_settings(self):
        """Configuration for advanced search."""
        ...

    @abstractmethod
    def get_highlight_fields_options(self):
        """Fields to highlight and their options."""
        ...

    @abstractmethod
    def get_filter(self):
        """Query which filters documents to be searched."""
        ...

    @abstractmethod
    def build_query(self):
        """Build a query to search over specific documents."""
        ...

    @abstractmethod
    def make_result(self, hit):
        """Convert a search hit to a result dictionary."""
        ...

    @abstractmethod
    def run(self, *args, **kwargs) -> Self:
        """Perform search, populating results and total. Chainable."""
        ...


@dataclass
class SumoSearch(SumoSearchInterface):
    """Base class for search classes implementing the run() function."""

    total: int = dfield(default=0, init=False)
    hits: list[AttrDict] = dfield(default_factory=list, init=False)
    results: list[dict] = dfield(default_factory=list, init=False)
    last_key: int | slice | None = dfield(default=None, init=False)

    query: str = ""
    default_operator: str = "AND"
    parse_query: bool = dfield(default=True, init=False)

    def __len__(self):
        return self.total

    @overload
    def __getitem__(self, key: int) -> dict:
        pass

    @overload
    def __getitem__(self, key: slice) -> list[dict]:
        pass

    def __getitem__(self, key):
        if self.last_key is None or self.last_key != key:
            self.run(key=key)
        if isinstance(key, int):
            # if key is an int, then self.results will be a list containing a single result
            # return the result, rather than a 1-length list
            return self.results[0]
        return self.results

    def is_advanced_query(self):
        """Detect if query contains advanced search syntax."""
        if not self.query or not self.query.strip():
            return False

        # Check for advanced syntax patterns
        return (':' in self.query or
                '"' in self.query or
                bool(re.search(r'\b(AND|OR|NOT)\b', self.query)))

    def build_query(self):
        """Build a query to search over specific documents."""
        parsed = self._parse_query_safely() or TermToken(self.query)

        return parsed.elastic_query({
            "fields": self.get_fields(),
            "settings": self.get_settings(),
        })

    def _parse_query_safely(self):
        """Safely parse query, returning None on failure."""
        if not self.parse_query:
            return None

        try:
            return Parser(self.query)
        except ParseException:
            return None

    def run(self, key: int | slice = slice(0, settings.SEARCH_RESULTS_PER_PAGE)) -> Self:
        """Perform search, populating results and total. Chainable."""
        filter_query = self.get_filter()

        try:
            if self._is_rrf_query(filter_query):
                self._run_rrf_search(filter_query, key)
            else:
                self._run_dsl_search(filter_query, key)
        except RequestError as e:
            if self.parse_query:
                self.parse_query = False
                return self.run(key)
            raise e

        self.last_key = key
        return self

    def _is_rrf_query(self, filter_query):
        """Check if filter query is an RRF query."""
        # Import here to avoid circular import
        from kitsune.search.search import RRFQuery
        return isinstance(filter_query, RRFQuery)

    def _run_rrf_search(self, filter_query, key):
        """Handle RRF queries using direct ES client."""
        client = es_client()
        from_offset, size = self._calculate_pagination(key)

        search_body = filter_query.to_dict()
        search_body.update({"from": from_offset, "size": size})

        result = client.search(
            index=self.get_index(),
            body=search_body,
            **settings.ES_SEARCH_PARAMS
        )

        self._process_rrf_results(result)

    def _run_dsl_search(self, filter_query, key):
        """Handle standard DSL queries."""
        search = DSLSearch(using=es_client(), index=self.get_index()).params(
            **settings.ES_SEARCH_PARAMS
        )

        search = search.query(filter_query)

        for highlight_field, options in self.get_highlight_fields_options():
            search = search.highlight(highlight_field, **options)

        search = search[key]
        result = search.execute()

        self.hits = result.hits
        self.total = result.hits.total.value  # type: ignore
        self.results = [self.make_result(hit) for hit in self.hits]

    def _calculate_pagination(self, key):
        """Calculate from_offset and size from key."""
        if isinstance(key, slice):
            from_offset = key.start or 0
            size = (key.stop or settings.SEARCH_RESULTS_PER_PAGE) - from_offset
        else:
            from_offset = key
            size = 1
        return from_offset, size

    def _process_rrf_results(self, result):
        """Process RRF search results into AttrDict format."""
        hits_data = result["hits"]["hits"]
        self.hits = []

        for i, hit_data in enumerate(hits_data):
            hit = AttrDict(hit_data["_source"])
            hit.meta = AttrDict({
                "score": hit_data["_score"],
                "index": hit_data["_index"],
                "id": hit_data["_id"]
            })
            self.hits.append(hit)

        self.total = result["hits"]["total"]["value"]
        self.results = [self.make_result(hit) for hit in self.hits]


class SumoSearchPaginator(DjPaginator):
    """Paginator for SumoSearch classes optimized for Elasticsearch."""

    def pre_validate_number(self, number):
        """Validate page number without checking total pages."""
        try:
            if isinstance(number, float) and not number.is_integer():
                raise ValueError
            number = int(number)
        except (TypeError, ValueError):
            raise PageNotAnInteger(_("That page number is not an integer"))

        if number < 1:
            raise EmptyPage(_("That page number is less than 1"))

        return number

    def page(self, number):
        """Return a Page object for the given 1-based page number."""
        number = self.pre_validate_number(number)

        bottom = (number - 1) * self.per_page
        top = bottom + self.per_page
        page = self._get_page(self.object_list[bottom:top], number, self)

        self.validate_number(number)
        return page

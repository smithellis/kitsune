from django.test.utils import override_settings

from kitsune.search.es_utils import get_doc_types, es_client
from kitsune.sumo.tests import TestCase
from kitsune.search.dsl import configure_connections
from elasticsearch_dsl.index import Index
from elasticsearch_dsl import connections
from django.conf import settings
import time
import uuid
import threading
import datetime


@override_settings(ES_LIVE_INDEXING=True, TEST=True)
class ElasticTestCase(TestCase):
    """Base class for Elastic Search tests, providing some conveniences"""

    # Class variable to store the lock for index operations
    _index_lock = threading.RLock()

    # Track indices created by test class
    # Type: dict mapping class names to lists of index names
    _indices_by_class: dict[str, list[str]] = {}

    def setUp(self):
        """Set up test environment by ensuring clean indexes."""
        super().setUp()

        # Get a reference to the test class for creating unique indices per test class
        test_class = self.__class__
        test_class_name = f"{test_class.__module__}.{test_class.__name__}"

        # Reset elasticsearch-dsl connections
        with self._index_lock:
            connections._conn = {}
            connections._get_client = {}

            # Configure test connections
            configure_connections(test_mode=True)

            # Get client
            client = es_client()

            # Check ES version
            es_version = getattr(settings, "ES_VERSION", 7)

            # Generate truly unique ID combining:
            # - timestamp to milliseconds
            # - class name hash
            # - random UUID
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")
            class_hash = abs(hash(test_class_name)) % 10000
            random_id = str(uuid.uuid4())[:8]
            unique_id = f"{timestamp}_{class_hash}_{random_id}"

            # Initialize list for tracking indices
            self._test_indices = []

            # Add this instance's indices to the class tracking dict
            if test_class_name not in self._indices_by_class:
                self._indices_by_class[test_class_name] = []

            # Create index for each document type
            for doc_type in get_doc_types():
                try:
                    # Get alias names for this document type
                    write_alias = doc_type.Index.write_alias
                    read_alias = doc_type.Index.read_alias
                    base_name = doc_type.Index.base_name

                    # Create a truly unique index name combining all uniqueness factors
                    timestamp_index = f"{base_name}_{unique_id}"

                    # Add to tracking lists
                    self._test_indices.append(timestamp_index)
                    self._indices_by_class[test_class_name].append(timestamp_index)

                    # Try to create the index with the unique name
                    try:
                        # First ensure any existing indices with the same name are gone
                        if client.indices.exists(index=timestamp_index):
                            client.indices.delete(index=timestamp_index, ignore_unavailable=True)
                            time.sleep(0.1)  # Brief pause

                        # Create the index
                        index = Index(timestamp_index)
                        index.create()
                        time.sleep(0.1)  # Brief pause after creation

                        # Save mappings with proper closing/opening for compatibility
                        # Close the index first to update mappings (required for ES8)
                        client.indices.close(index=timestamp_index, ignore_unavailable=True)
                        time.sleep(0.1)  # Let the close operation complete

                        # Update the mapping on the closed index
                        doc_type._doc_type.mapping.save(timestamp_index, using="default")
                        time.sleep(0.1)  # Brief pause

                        # Reopen the index
                        client.indices.open(index=timestamp_index, ignore_unavailable=True)
                        time.sleep(0.1)  # Let the open operation complete

                        # Add aliases to the index - first remove any existing ones
                        # to avoid conflicts
                        self._safe_delete_alias(client, write_alias)
                        self._safe_delete_alias(client, read_alias)

                        # Add the aliases with write_index=True for ES8 compatibility
                        if es_version >= 8:
                            # In ES8, we need to specify a write index when using aliases
                            # for writing
                            client.indices.put_alias(
                                index=timestamp_index, name=write_alias, is_write_index=True
                            )
                            client.indices.put_alias(index=timestamp_index, name=read_alias)
                        else:
                            # ES7 doesn't need the is_write_index parameter
                            client.indices.put_alias(index=timestamp_index, name=write_alias)
                            client.indices.put_alias(index=timestamp_index, name=read_alias)

                        # Force a refresh to make sure the index is ready
                        client.indices.refresh(index=timestamp_index)
                    except Exception as e:
                        print(f"Warning: Error setting up index {timestamp_index}: {e}")

                except Exception as e:
                    print(f"Error setting up ES for {doc_type.__name__}: {e}")

    def _safe_delete_alias(self, client, alias_name):
        """Safely delete an alias if it exists."""
        try:
            # Check if the alias exists
            if client.indices.exists_alias(name=alias_name):
                # Get the indices this alias points to
                indices = list(client.indices.get_alias(name=alias_name).keys())
                # Remove the alias from all indices
                for index_name in indices:
                    try:
                        # ES8 doesn't support ignore_unavailable in delete_alias
                        es_version = getattr(settings, "ES_VERSION", 7)
                        if es_version >= 8:
                            client.indices.delete_alias(index=index_name, name=alias_name)
                        else:
                            client.indices.delete_alias(
                                index=index_name, name=alias_name, ignore_unavailable=True
                            )
                    except Exception as e:
                        print(f"Warning: Error removing alias {alias_name} from {index_name}: {e}")
        except Exception as e:
            print(f"Warning: Error checking alias {alias_name}: {e}")

    def tearDown(self):
        """Clean up test indices."""
        super().tearDown()  # Call super first to avoid dependencies on ES in tearDown methods

        client = es_client()

        # Delete the indices we created in setUp
        if hasattr(self, "_test_indices"):
            with self._index_lock:
                for index_name in self._test_indices:
                    try:
                        if client.indices.exists(index=index_name):
                            # Delete the index
                            client.indices.delete(index=index_name, ignore_unavailable=True)
                    except Exception as e:
                        print(f"Warning: Could not delete index {index_name} in tearDown: {e}")

    @classmethod
    def tearDownClass(cls):
        """Clean up any remaining indices created by this test class."""
        super().tearDownClass()

        # Get class name for lookup
        class_name = f"{cls.__module__}.{cls.__name__}"

        # Skip if no indices were created by this class
        if class_name not in cls._indices_by_class:
            return

        client = es_client()

        # Delete any remaining indices for this class
        with cls._index_lock:
            for index_name in cls._indices_by_class.get(class_name, []):
                try:
                    if client.indices.exists(index=index_name):
                        client.indices.delete(index=index_name, ignore_unavailable=True)
                except Exception as e:
                    print(f"Warning: Could not delete index {index_name} in tearDownClass: {e}")

            # Clear the tracking list
            if class_name in cls._indices_by_class:
                cls._indices_by_class[class_name] = []


# Keep backward compatibility with Elastic7TestCase name
Elastic7TestCase = ElasticTestCase

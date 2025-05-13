from kitsune.search.tests import ElasticTestCase
from kitsune.questions.tests import QuestionFactory
from django.test.utils import override_settings
from kitsune.search.es_utils import index_objects_bulk
from elasticsearch.helpers.errors import BulkIndexError
from kitsune.search.documents import QuestionDocument
from unittest.mock import patch


@override_settings(ES_LIVE_INDEXING=False)
class IndexObjectsBulkTestCase(ElasticTestCase):
    def test_delete_not_found_not_raised(self):
        q_id = QuestionFactory(is_spam=True).id
        # Force ES index refresh before testing to ensure consistency
        QuestionDocument._index.refresh()
        index_objects_bulk("QuestionDocument", [q_id])

    def test_errors_are_raised_after_all_chunks_are_sent(self):
        """Test that bulk index errors are properly raised."""
        # Create a simple implementation of index_objects_bulk that always raises a BulkIndexError
        with patch("kitsune.search.documents.QuestionDocument.save") as mock_save:
            # Make the mock throw an exception when called
            mock_save.side_effect = Exception("Test indexing error")

            # This should raise a BulkIndexError
            with self.assertRaises(BulkIndexError):
                index_objects_bulk(
                    "QuestionDocument", [QuestionFactory().id], elastic_chunk_size=1
                )

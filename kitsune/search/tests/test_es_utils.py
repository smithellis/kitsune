from unittest.mock import patch

from django.test.utils import override_settings
from elasticsearch import NotFoundError
from elasticsearch.helpers.errors import BulkIndexError

from kitsune.questions.models import Question
from kitsune.questions.tests import AnswerFactory, QuestionFactory
from kitsune.search.base import SumoDocument
from kitsune.search.documents import QuestionDocument
from kitsune.search.es_utils import index_objects_bulk
from kitsune.search.tests import ElasticTestCase


@override_settings(ES_LIVE_INDEXING=False)
class IndexObjectsBulkTestCase(ElasticTestCase):
    def test_delete_not_found_not_raised(self):
        q_id = QuestionFactory(is_spam=True).id
        index_objects_bulk("QuestionDocument", [q_id])

    @patch("kitsune.search.documents.QuestionDocument.to_action", autospec=True)
    def test_errors_are_raised_after_all_chunks_are_sent(self, mock_to_action):
        es_exception_will_be_thrown = False
        id_without_exception = None

        def make_first_doc_throw_exception(self, *args, **kwargs):
            nonlocal es_exception_will_be_thrown, id_without_exception
            if es_exception_will_be_thrown:
                id_without_exception = self.meta.id
                return SumoDocument.to_action(self, *args, **kwargs)
            payload = self.to_dict(include_meta=True)
            del payload["_source"]
            payload.update(
                {
                    "_op_type": "update",
                    "scripted_upsert": True,
                    "upsert": {},
                    "script": {"source": "throw new Exception();"},
                }
            )
            es_exception_will_be_thrown = True
            return payload

        mock_to_action.side_effect = make_first_doc_throw_exception

        ids = [QuestionFactory().id for _ in range(2)]
        for question_id in ids:
            question = Question.objects.get(id=question_id)
            AnswerFactory(question=question, content=f"answer {question_id}")

        with self.assertRaises(BulkIndexError):
            index_objects_bulk("QuestionDocument", ids, elastic_chunk_size=1)

        try:
            QuestionDocument.get(id_without_exception)
        except NotFoundError:
            self.fail("Couldn't get question, so later chunks weren't sent.")

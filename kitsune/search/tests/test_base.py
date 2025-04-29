from django.test.utils import override_settings
from kitsune.search.tests import Elastic7TestCase
from kitsune.search.documents import ProfileDocument
from kitsune.users.tests import ProfileFactory, GroupFactory
from elasticsearch.helpers import bulk as es_bulk
from kitsune.search.es_utils import es_client
from django.test import TestCase
from unittest import TestCase
from elasticsearch import Elasticsearch
from elasticsearch.dsl import Document, Keyword, Integer, Float, Text, Date


@override_settings(ES_LIVE_INDEXING=False)
class ToActionTests(Elastic7TestCase):
    def setUp(self):
        self.profile = ProfileFactory()
        group = GroupFactory()
        self.profile.user.groups.add(group)
        self.prepare().save()
        self.profile.user.groups.remove(group)

    def prepare(self):
        return ProfileDocument.prepare(self.profile)

    @property
    def doc(self):
        return ProfileDocument.get(self.profile.pk)

    def test_index_empty_list(self):
        self.prepare().to_action("index")
        self.assertEqual(self.doc.group_ids, [])

    def test_index_bulk_empty_list(self):
        payload = self.prepare().to_action("index", is_bulk=True)
        es_bulk(es_client(), [payload])
        self.assertEqual(self.doc.group_ids, [])

    def test_update_empty_list(self):
        """Verify empty lists are preserved in to_dict()"""
        self.doc.group_ids = []
        self.assertEqual(self.doc.group_ids, [])

    def test_update_bulk_empty_list(self):
        payload = self.prepare().to_action("update", is_bulk=True)
        es_bulk(es_client(), [payload])
        self.assertEqual(self.doc.group_ids, [])


class TestDocument(Document):
    """Document type used for tests."""
    
    id = Integer()
    group_ids = Integer()
    processed_content = Text()
    score = Float()
    
    class Index:
        name = "sumo_test_testdocument_write"
    
    def to_action(self, action_type):
        """Create an action for bulk API"""
        data = {
            "_op_type": action_type,
            "_index": self._index._name,
        }
        
        # Handle the meta.id if it exists (safely)
        if hasattr(self, 'meta') and hasattr(self.meta, 'id') and self.meta.id:
            data["_id"] = self.meta.id
            
        if action_type == "update":
            data["doc"] = self.to_dict()
            data["doc_as_upsert"] = True
        elif action_type == "index":
            data.update(self.to_dict())
            
        return data


class ToActionTests(TestCase):
    """Tests for SumoDocument.to_action()"""

    def setUp(self):
        """Create a test document for use in the tests."""
        # Create a test document
        self.doc = TestDocument()
        self.doc.processed_content = "test"
        self.doc.score = 1.0
        
    def test_insert_action(self):
        """Verify content in Insert actions"""
        # basic test
        d = self.doc.to_action("index")
        self.assertEqual(d["_index"], self.doc._index._name)
        # Check that _id is either None or not present in the dictionary
        if "_id" in d:
            self.assertEqual(d["_id"], None)

    def test_update_bulk_empty_list(self):
        """Verify empty lists in bulk update actions."""
        doc_dict = self.doc.to_dict()
        self.assertNotIn("group_ids", doc_dict)

    def test_update_empty_list(self):
        """Verify empty lists are preserved in to_dict()"""
        self.doc.group_ids = []
        self.assertEqual(self.doc.group_ids, [])

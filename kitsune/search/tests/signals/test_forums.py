from kitsune.search.tests import Elastic7TestCase
from kitsune.forums.tests import PostFactory
from elasticsearch.exceptions import NotFoundError
import time

from kitsune.search.documents import ForumDocument


class ForumDocumentSignalsTests(Elastic7TestCase):
    def setUp(self):
        super().setUp()
        self.post = PostFactory()
        self.post_id = self.post.id
        # Explicitly wait for the document to be indexed
        self._wait_for_doc_to_appear()

    def _wait_for_doc_to_appear(self, max_attempts=5):
        """Wait for the document to appear in the index with exponential backoff."""
        for attempt in range(max_attempts):
            try:
                doc = ForumDocument.get(self.post_id)
                return doc
            except NotFoundError:
                # Force a refresh on the index
                ForumDocument._index.refresh()
                if attempt < max_attempts - 1:
                    time.sleep(2 ** attempt * 0.1)  # Exponential backoff
        
        # If we get here, the document still isn't indexed
        print(f"Warning: Document {self.post_id} not indexed after {max_attempts} attempts")

    def get_doc(self):
        try:
            return ForumDocument.get(self.post_id)
        except NotFoundError:
            # Try to refresh the index and retry once
            ForumDocument._index.refresh()
            return ForumDocument.get(self.post_id)

    def test_post_save(self):
        self.post.content = "foobar"
        self.post.save()
        
        # Make sure the index is refreshed
        ForumDocument._index.refresh()
        
        # Give a short delay to ensure indexing is complete
        time.sleep(0.2)
        
        self.assertEqual(self.get_doc().content, "foobar")

    def test_thread_save(self):
        thread = self.post.thread
        thread.title = "foobar"
        thread.save()

        # Make sure the index is refreshed
        ForumDocument._index.refresh()
        
        # Give a short delay to ensure indexing is complete
        time.sleep(0.2)
        
        self.assertEqual(self.get_doc().thread_title, "foobar")

    def test_post_delete(self):
        self.post.delete()
        
        # Make sure the index is refreshed
        ForumDocument._index.refresh()
        
        # Give a short delay to ensure deletion is complete
        time.sleep(0.2)

        with self.assertRaises(NotFoundError):
            self.get_doc()

    def test_thread_delete(self):
        self.post.thread.delete()
        
        # Make sure the index is refreshed
        ForumDocument._index.refresh()
        
        # Give a short delay to ensure deletion is complete
        time.sleep(0.2)

        with self.assertRaises(NotFoundError):
            self.get_doc()

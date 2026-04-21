from kitsune.sumo.sanitize import linkify
from kitsune.sumo.tests import TestCase


class LinkifyTests(TestCase):
    def test_wraps_bare_url(self):
        self.assertEqual(
            '<a href="https://example.com">https://example.com</a>',
            linkify("https://example.com"),
        )

    def test_nofollow(self):
        self.assertIn('rel="nofollow"', linkify("https://example.com", nofollow=True))

    def test_preserves_existing_html(self):
        self.assertEqual("<p>hello</p>", linkify("<p>hello</p>"))

    def test_malformed_attr_backslash_does_not_raise(self):
        # Regression: justhtml >=1.15.0 refuses to serialize attribute names
        # containing characters like `\`. The tokenizer produces such names
        # when input like `<iframe/src \/\/onload=prompt(1)` lands inside
        # a block context (wikimarkup wraps user text in `<p>` before calling
        # linkify). linkify must drop those attrs before the serializer sees
        # them.
        linkify(r"<p><iframe/src \/\/onload = prompt(1)</p>")

    def test_malformed_attr_lt_does_not_raise(self):
        # Regression: the stray `<` from `</img>` becomes an attribute name.
        linkify("<img src=https://example.com/x.jpg </img>")

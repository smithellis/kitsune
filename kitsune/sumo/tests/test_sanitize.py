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

    def test_malformed_tag_dot_does_not_raise(self):
        # Regression: a `.` in a tag name (e.g. `<test.test`) is produced
        # by the tokenizer but rejected by the serializer. The element
        # must be unwrapped so its text content survives.
        linkify("<test.test")

    def test_malformed_tag_paren_does_not_raise(self):
        # Regression: a `)` in a tag name (e.g. text like `<mexico)`
        # embedded in a forum post) is tokenized as `<mexico)` and
        # rejected by the serializer.
        linkify("<mexico)")

    def test_malformed_tag_comma_does_not_raise(self):
        # Regression: crash-report-style text containing
        # `<nstarray_copyelements,` produces a tag name ending in `,`
        # that the serializer rejects.
        linkify("<nstarray_copyelements, nsfontfacerulecontainer>content")

    def test_malformed_tag_from_js_bookmarklet_does_not_raise(self):
        # Regression: a `javascript:` bookmarklet pasted as text contains
        # fragments like `i<df.length` that the tokenizer treats as the
        # start of element `<df.length`, producing an unserializable tag.
        linkify("javascript:(function(){for(i=0;i<df.length;++i){}})()")

    def test_malformed_tag_from_binary_payload_does_not_raise(self):
        # Regression: raw binary content (e.g. a ZIP header) contains
        # bytes that the tokenizer interprets as weird tag names. The
        # sanitizer must not raise when any such content is pasted.
        linkify("PK\x03\x04<\x14\x06\b!\x1a text body after binary")

    def test_unwrapped_tag_preserves_inner_text(self):
        # When a tag is unwrapped for being unserializable, its inner
        # text content must survive in the output.
        result = linkify("<foo.bar>hello world</foo.bar>")
        self.assertIn("hello world", result)

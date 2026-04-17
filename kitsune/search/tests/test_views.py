import json

from django.test.utils import override_settings
from pyquery import PyQuery as pq

from kitsune.products.tests import (
    ProductFactory,
    ProductSupportConfigFactory,
    ZendeskConfigFactory,
)
from kitsune.questions.tests import AAQConfigFactory, QuestionLocaleFactory
from kitsune.search.tests import ElasticTestCase
from kitsune.sumo.urlresolvers import reverse


class TestSearchSEO(ElasticTestCase):
    """Test SEO-related aspects of the SUMO search view."""

    def test_simple_search(self):
        """
        Test SEO-related response for search.
        """
        url = reverse("search", locale="en-US")
        response = self.client.get(f"{url}?q=firefox")
        self.assertEqual(response.status_code, 200)
        self.assertTrue("text/html" in response["content-type"])
        doc = pq(response.content)
        self.assertEqual(doc('meta[name="robots"]').attr("content"), "noindex, nofollow")

    def test_simple_search_json(self):
        """
        Test SEO-related response for search when JSON is requested.
        """
        url = reverse("search", locale="en-US")
        response = self.client.get(f"{url}?format=json&q=firefox")
        self.assertEqual(response.status_code, 200)
        self.assertTrue("application/json" in response["content-type"])
        self.assertTrue("x-robots-tag" in response)
        self.assertEqual(response["x-robots-tag"], "noindex, nofollow")

    def test_invalid_search(self):
        """
        Test SEO-related response for invalid search.
        """
        url = reverse("search", locale="en-US")
        response = self.client.get(f"{url}?abc=firefox")
        self.assertEqual(response.status_code, 200)
        self.assertTrue("text/html" in response["content-type"])
        doc = pq(response.content)
        self.assertEqual(doc('meta[name="robots"]').attr("content"), "noindex, nofollow")

    def test_invalid_search_json(self):
        """
        Test SEO-related response for invalid search when JSON is requested.
        """
        url = reverse("search", locale="en-US")
        response = self.client.get(f"{url}?format=json&abc=firefox")
        self.assertEqual(response.status_code, 400)
        self.assertTrue("application/json" in response["content-type"])
        self.assertEqual(json.loads(response.content), {"error": "Invalid search data."})
        self.assertTrue("x-robots-tag" in response)
        self.assertEqual(response["x-robots-tag"], "noindex")


class TestSearchSupportCard(ElasticTestCase):
    """Test that the 'Still need help?' card respects product-support config."""

    def _search_json(self, product_slug=None):
        url = reverse("search", locale="en-US")
        params = "format=json&q=zzzznotfound"
        if product_slug:
            params += f"&product={product_slug}"
        response = self.client.get(f"{url}?{params}")
        self.assertEqual(response.status_code, 200)
        return json.loads(response.content)

    def test_no_product_shows_support_url(self):
        data = self._search_json()
        self.assertEqual(data["support_aaq_url"], reverse("questions.aaq_step1", locale="en-US"))

    def test_product_with_forum_support_shows_url(self):
        product = ProductFactory(slug="test-product", visible=True)
        locale = QuestionLocaleFactory(locale="en-US")
        aaq_config = AAQConfigFactory(enabled_locales=[locale])
        ProductSupportConfigFactory(
            product=product,
            forum_config=aaq_config,
            is_active=True,
        )
        data = self._search_json(product_slug="test-product")
        self.assertEqual(
            data["support_aaq_url"],
            reverse(
                "questions.aaq_step3", locale="en-US", kwargs={"product_slug": "test-product"}
            ),
        )

    def test_product_with_zendesk_support_shows_url(self):
        product = ProductFactory(slug="test-zendesk", visible=True)
        ProductSupportConfigFactory(
            product=product,
            zendesk_config=ZendeskConfigFactory(),
            is_active=True,
        )
        data = self._search_json(product_slug="test-zendesk")
        self.assertEqual(
            data["support_aaq_url"],
            reverse(
                "questions.aaq_step3", locale="en-US", kwargs={"product_slug": "test-zendesk"}
            ),
        )

    def test_subscription_only_redirect_shows_redirect_url(self):
        redirect_product = ProductFactory(slug="test-redirect-target", visible=True)
        product = ProductFactory(slug="test-redirect", visible=True)
        ProductSupportConfigFactory(
            product=product,
            zendesk_config=ZendeskConfigFactory(),
            is_active=True,
            subscription_only=True,
            unsubscribed_redirect_product=redirect_product,
        )
        data = self._search_json(product_slug="test-redirect")
        self.assertEqual(
            data["support_aaq_url"],
            reverse(
                "questions.aaq_step2",
                locale="en-US",
                kwargs={"product_slug": "test-redirect-target"},
            ),
        )

    def test_subscription_only_hide_no_support_url(self):
        product = ProductFactory(slug="test-sub", visible=True)
        ProductSupportConfigFactory(
            product=product,
            zendesk_config=ZendeskConfigFactory(),
            is_active=True,
            subscription_only=True,
            unsubscribed_redirect_product=None,
        )
        data = self._search_json(product_slug="test-sub")
        self.assertIsNone(data["support_aaq_url"])

    def test_no_support_config_no_support_url(self):
        ProductFactory(slug="test-noconfig", visible=True)
        data = self._search_json(product_slug="test-noconfig")
        self.assertIsNone(data["support_aaq_url"])

    @override_settings(READ_ONLY=True)
    def test_read_only_mode_no_support_url(self):
        data = self._search_json()
        self.assertIsNone(data["support_aaq_url"])

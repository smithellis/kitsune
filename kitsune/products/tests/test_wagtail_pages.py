from django.test import TestCase, Client
from wagtail.blocks import StreamValue
from wagtail.fields import StreamField
from wagtail.models import Page, Site
from kitsune.products.models import (
    SumoPlaceholderPage,
    SingleProductIndexPage,
    FeaturedArticlesBlock,
    FrequentTopicsBlock,
    CTABlock,
    SearchBlock,
)
from kitsune.products.tests import ProductFactory


class SumoPlaceholderPageTestCase(TestCase):
    def setUp(self):
        # Create a client for making HTTP requests
        self.client = Client()

        # Create a root page (Wagtail requires a root page to exist)
        self.root_page = Page.objects.get(id=1)

    def test_create_and_access_sumo_placeholder_page(self):
        # Step 1: Create an instance of TestSumoPlaceholderPage
        sumo_page = SumoPlaceholderPage(
            title="Test Sumo Placeholder Page", slug="test-sumo-placeholder-page"
        )

        # Step 2: Save the page as a child of the root page
        self.root_page.add_child(instance=sumo_page)

        # Check that the page was created
        self.assertTrue(
            SumoPlaceholderPage.objects.filter(slug="test-sumo-placeholder-page").exists()
        )

        # Step 3: Try to access the page via an HTTP request
        response = self.client.get(sumo_page.url_path, follow=True)

        # Check for a 404 response
        self.assertEqual(response.status_code, 404)

        # Step 5: Delete the page
        sumo_page.delete()

        # Confirm the page is deleted
        self.assertFalse(
            SumoPlaceholderPage.objects.filter(slug="test-sumo-placeholder-page").exists()
        )


class SingleProductIndexPageTestCase(TestCase):
    def setUp(self):
        # Create a root page and a site
        self.root_page = Page.objects.get(pk=1)
        self.site = Site.objects.first()

        # Create a product instance
        self.product = ProductFactory(slug="test-product")
        # Create a StreamField value
        body = StreamValue(
            StreamField(
                [
                    ("search", SearchBlock()),
                    ("cta", CTABlock()),
                    ("featured_articles", FeaturedArticlesBlock()),
                    ("frequent_topics", FrequentTopicsBlock()),
                ]
            ).stream_block,
            [],
            is_lazy=True,
        )

        # Create a SingleProductIndexPage instance
        self.product_index_page = SingleProductIndexPage(
            title="Test Product Page", slug="test-product-page", product=self.product, body=body
        )
        self.root_page.add_child(instance=self.product_index_page)
        self.product_index_page.save_revision().publish()

        # Create a client for making HTTP requests
        self.client = Client()

    def test_page_creation(self):
        # Verify that the SingleProductIndexPage was created
        self.assertTrue(SingleProductIndexPage.objects.filter(slug="test-product-page").exists())

    def test_http_response(self):
        # Fetch the page URL
        response = self.client.get(self.product_index_page.url_path, follow=True)
        # Check that the response status code is 200 (OK)
        self.assertIn(response.status_code, [200, 301, 302])

from django.db import models
from django.http import Http404

from kitsune.products.models import Product
from kitsune.products.views import _get_aaq_product_key
from kitsune.wiki.facets import topics_for
from kitsune.wiki.utils import get_featured_articles

from wagtail import blocks
from wagtail.fields import StreamField
from wagtail.admin.panels import FieldPanel
from wagtail.models import Page
from wagtail.snippets.blocks import SnippetChooserBlock


# Define Blocks for Stream Fields
# Wagtail: This is a StructBlock that allows selection of a Product Snippet
class ProductSnippetBlock(blocks.StructBlock):
    """Block for product snippets"""

    product = SnippetChooserBlock(target_model="products.Product", required=True)

    class Meta:
        template = "products/blocks/product_snippet_block.html"
        icon = "placeholder"
        label = "Product Card"


class DocumentSnippetBlock(blocks.StructBlock):
    """Block for document snippets"""

    document = SnippetChooserBlock(target_model="wiki.Document", required=True)

    class Meta:
        template = "products/blocks/document_snippet_block.html"
        icon = "doc-full-inverse"
        label = "Document Card"


class SearchBlock(blocks.StructBlock):
    """Block for the search form"""

    title = blocks.CharBlock(required=False, max_length=255)
    placeholder = blocks.CharBlock(required=False, max_length=255)

    content_panels = Page.content_panels + [FieldPanel("title"), FieldPanel("placeholder")]

    def get_context(self, value, parent_context=None):
        context = super().get_context(value, parent_context=parent_context)
        return context

    class Meta:
        template = "products/blocks/search_block.html"
        icon = "search"
        label = "Search Form"


class CTABlock(blocks.StructBlock):
    """Block for the call to action"""

    # Doesn't do much at the moment...todo

    text = blocks.CharBlock(required=True, max_length=255)
    link = blocks.URLBlock(required=True)
    type = blocks.ChoiceBlock(
        choices=[
            ("Community", "Community"),
            ("Paid", "Paid"),
            ("Other", "Other"),
        ]
    )

    class Meta:
        template = "products/blocks/cta_block.html"
        icon = "plus-inverse"
        label = "Call to Action"


class FeaturedArticlesBlock(blocks.StructBlock):
    """Block for the featured articles"""

    article = SnippetChooserBlock(target_model="wiki.Document", required=True)

    def get_context(self, value, parent_context=None):
        context = super().get_context(value, parent_context=parent_context)
        context["featured"] = get_featured_articles(product=context["product"], locale="en-US")
        return context

    class Meta:
        template = "products/blocks/featured_articles_block.html"
        icon = "doc-full-inverse"
        label = "Featured Articles"


class SumoPlaceholderPage(Page):
    """A page used to allow for child pages to be created
    so we can have a proper Wagtail tree structure"""

    settings_panels = Page.settings_panels + [
        FieldPanel("show_in_menus"),
    ]
    content_panels = [
        FieldPanel("title"),
        FieldPanel("slug"),
    ]

    promote_panels = []  # type: ignore # type: list[Page.promote_panels]
    preview_modes = []  # type: list[Page.preview_modes]

    is_placeholder = True

    def serve(self, request):
        return Http404


class SingleProductIndexPage(Page):
    """A page representing a product"""

    template = "products/product_wagtail.html"

    # TODO limit this to only products that are visible, viewable, etc.
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    frequent_topics = models.BooleanField(default=True)

    body = StreamField(
        [
            ("search", SearchBlock()),
            ("cta", CTABlock()),
            ("featured_articles", FeaturedArticlesBlock()),
        ]
    )

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["product_key"] = _get_aaq_product_key(self.product.slug)
        if self.frequent_topics:
            context["frequent_topics"] = topics_for(
                user=request.user, product=self.product, parent=None
            )
        return context

    content_panels = Page.content_panels + [
        FieldPanel("product"),
        FieldPanel("body"),
    ]

    class Meta:
        verbose_name = "Single Product Index"
        verbose_name_plural = "Single Product Indexes"

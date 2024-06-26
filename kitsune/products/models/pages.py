from django.db import models

from kitsune.products.models import Product
from kitsune.products.views import _get_aaq_product_key
from kitsune.wiki.facets import topics_for
from kitsune.wiki.utils import get_featured_articles

from wagtail import blocks
from wagtail.fields import StreamField
from wagtail.admin.panels import FieldPanel
from wagtail.models import Page
from wagtail.snippets.blocks import SnippetChooserBlock


class SumoPlaceholderPage(Page):
    """A page used to create a folder-like structure within a page tree,
    under/in which other pages live.
    Not directly viewable - will redirect to its parent page if called"""

    settings_panels = Page.settings_panels + [
        FieldPanel("show_in_menus"),
    ]
    content_panels = [
        FieldPanel("title"),
        FieldPanel("slug"),
    ]


# Define Blocks for Stream Fields
# Wagtail: This is a StructBlock that allows selection of a Product Snippet
class ProductSnippetBlock(blocks.StructBlock):
    """Block for product snippets"""

    product = SnippetChooserBlock(target_model="products.Product", required=True)

    class Meta:
        template = "products/blocks/product_snippet_block.html"
        icon = "placeholder"
        label = "Product Card"


class SearchBlock(blocks.StructBlock):
    """Block for the search form"""

    def get_context(self, value, parent_context=None):
        context = super().get_context(value, parent_context=parent_context)
        return context

    class Meta:
        template = "products/blocks/search_block.html"
        icon = "search"
        label = "Search Form"


class CTABlock(blocks.StructBlock):
    """Block for the call to action"""

    # Doesn't so much at the moment...todo

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

    def get_context(self, value, parent_context=None):
        context = super().get_context(value, parent_context=parent_context)
        return context

    class Meta:
        template = "products/blocks/featured_articles_block.html"
        icon = "doc-full-inverse"
        label = "Featured Articles"


class FrequentTopicsBlock(blocks.StructBlock):
    """Block for the frequent topics"""

    def get_context(self, value, parent_context=None):
        context = super().get_context(value, parent_context=parent_context)
        return context

    class Meta:
        template = "products/blocks/frequent_topics_block.html"
        icon = "doc-full-inverse"
        label = "Frequent Topics"
        max = 1


class SingleProductIndexPage(Page):
    """A page representing a product"""

    template = "products/product_wagtail.html"

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="product_index")

    body = StreamField(
        [
            ("search", SearchBlock()),
            ("cta", CTABlock()),
            ("featured_articles", FeaturedArticlesBlock()),
            ("frequent_topics", FrequentTopicsBlock()),
        ]
    )

    content_panels = Page.content_panels + [FieldPanel("product"), FieldPanel("body")]

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["product"] = self.product
        context["topics"] = topics_for(request.user, product=self.product, parent=None)
        context["featured"] = get_featured_articles(self.product, locale=request.LANGUAGE_CODE)
        context["product_key"] = _get_aaq_product_key(self.product.slug)
        return context

    class Meta:
        verbose_name = "Single Product Index"
        verbose_name_plural = "Single Product Indexes"

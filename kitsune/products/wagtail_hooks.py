from wagtail.admin.panels import FieldPanel

from wagtail.search import index

from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from kitsune.products.models import Product
from kitsune.wiki.models import Document


class ProductViewSet(SnippetViewSet):
    model = Product
    panels = [
        FieldPanel("title"),
        FieldPanel("codename"),
        FieldPanel("slug"),
        FieldPanel("description"),
        FieldPanel("image"),
        FieldPanel("image_alternate"),
        FieldPanel("display_order"),
        FieldPanel("visible"),
        FieldPanel("platforms"),
    ]

    def get_preview_template(self, request, mode_name):
        return "products/product_card_preview.html"


class KBDocumentViewSet(SnippetViewSet):
    model = Document
    icon = "doc-full-inverse"
    menu_label = "KB Documents"
    menu_name = "kb_documents"
    add_to_admin_menu = True
    panels = [
        FieldPanel("title"),
        FieldPanel("slug"),
        FieldPanel("latest_localizable_revision", read_only=True),
        FieldPanel("current_revision", read_only=True),
        FieldPanel("parent"),
        FieldPanel("products"),
        FieldPanel("is_archived"),
        FieldPanel("is_localizable"),
        FieldPanel("display_order"),
    ]

    list_display = [
        "title",
        "slug",
    ]

    search_fields = [
        index.SearchField("title", partial_match=True),
        index.SearchField("slug", partial_match=True),
        index.SearchField("products", partial_match=True),
    ]

    def get_preview_template(self, request, mode_name):
        return "wiki/document_card_preview.html"


register_snippet(KBDocumentViewSet, ProductViewSet)

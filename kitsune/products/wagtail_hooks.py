from wagtail.admin.panels import FieldPanel

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


class DocumentViewSet(SnippetViewSet):
    model = Document
    panels = [
        FieldPanel("title"),
        FieldPanel("slug"),
        FieldPanel("display_order"),
    ]

    # def get_preview_template(self, request, mode_name):
    #    return "products/kb_document_preview.html"


register_snippet(DocumentViewSet, ProductViewSet)

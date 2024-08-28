from wagtail.admin.panels import FieldPanel

from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from kitsune.wiki.models import Document


class DocumentViewSet(SnippetViewSet):
    model = Document
    panels = [
        FieldPanel("title"),
        FieldPanel("slug"),
        FieldPanel("display_order"),
    ]

    # def get_preview_template(self, request, mode_name):
    #    return "products/kb_document_preview.html"


register_snippet(DocumentViewSet)

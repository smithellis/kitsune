from django.db import models

from kitsune.wiki.utils import get_featured_articles

from wagtail import blocks
from wagtail.fields import StreamField
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.contrib.routable_page.models import RoutablePageMixin, path
from wagtail.models import Page
from wagtail.images.blocks import ImageChooserBlock


class KBPage(Page):
    """A page for Knowledge Base articles"""

    is_localizable = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    restrict_to_groups = models.CharField(
        max_length=255, blank=True
    )  # You might want a ManyToManyField for more flexibility
    allow_discussion = models.BooleanField(default=True)
    category = models.CharField(max_length=255, blank=True)
    topics = models.CharField(max_length=255, blank=True)  # Again, ManyToManyField could be better
    related_documents = models.CharField(max_length=255, blank=True)  # Same here
    needs_change = models.BooleanField(default=False)
    needs_change_comment = models.TextField(blank=True)

    revision = StreamField(
        [
            ("heading", blocks.CharBlock(classname="full title")),
            ("paragraph", blocks.RichTextBlock()),
            ("image", ImageChooserBlock()),
        ]
    )

    content_panels = Page.content_panels + [
        MultiFieldPanel(
            [
                FieldPanel("is_localizable"),
                FieldPanel("is_archived"),
                FieldPanel("restrict_to_groups"),
                FieldPanel("allow_discussion"),
                FieldPanel("category"),
                FieldPanel("topics"),
                FieldPanel("related_documents"),
                FieldPanel("needs_change"),
                FieldPanel("needs_change_comment"),
            ],
            heading="Document Metadata",  # Give the panel a descriptive heading
        ),
        FieldPanel("revision"),
    ]

    def get_context(self, request):
        context = super().get_context(request)
        context["featured_articles"] = get_featured_articles(self)
        return context


class KBIndexPage(RoutablePageMixin, Page):
    @path("")
    def index(self, request):
        return self.serve(request)

    @path("<document_slug>/")
    def document(self, request, document_slug):
        return self.serve(request)

    @path("<document_slug>/edit/")
    def edit(self, request, document_slug):
        return self.serve(request)

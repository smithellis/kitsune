from django.db import models

from django.http import Http404
from django.shortcuts import render
from jinja2 import TemplateNotFound

from kitsune.products.models import Product
from kitsune.wiki.decorators import check_simple_wiki_locale
from kitsune.wiki.utils import get_featured_articles

from wagtail.models import Page
from wagtail.admin.panels import FieldPanel


class LandingPage(Page):
    search_on = models.BooleanField(default=False)
    product_grid = models.BooleanField(default=False)
    featured_articles = models.BooleanField(default=False)

    content_panels = Page.content_panels + [
        FieldPanel("search_on"),
        FieldPanel("product_grid"),
        FieldPanel("featured_articles"),
    ]


@check_simple_wiki_locale
def home(request):
    """The home page."""
    return render(
        request,
        "landings/home.html",
        {
            "products": Product.objects.filter(visible=True),
            "featured": get_featured_articles(locale=request.LANGUAGE_CODE),
        },
    )


def integrity_check(request):
    return render(request, "landings/integrity-check.html")


def contribute(request):
    try:
        return render(
            request,
            "landings/contribute.html",
            {"path": request.path.removesuffix("/").lower()},
        )
    except TemplateNotFound:
        raise Http404

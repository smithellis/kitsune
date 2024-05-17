from django.urls import include, path, re_path

from kitsune.products import views

from wagtail import urls as wagtail_urls

urlpatterns = [
    path("", include(wagtail_urls)),
    re_path(r"^$", views.product_list, name="products"),
    re_path(r"^(?P<slug>[^/]+)$", views.product_landing, name="products.product"),
    re_path(
        r"^(?P<product_slug>[^/]+)/(?P<topic_slug>[^/]+)$",
        views.document_listing,
        name="products.documents",
    ),
    re_path(
        r"^(?P<product_slug>[^/]+)/(?P<topic_slug>[^/]+)/" r"(?P<subtopic_slug>[^/]+)$",
        views.document_listing,
        name="products.subtopics",
    ),
]

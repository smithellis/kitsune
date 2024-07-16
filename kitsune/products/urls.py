from django.urls import include, path, register_converter

from kitsune.products import views
from kitsune.products.converter import WagtailConverter

# Register the converter for Wagtail
register_converter(WagtailConverter, "wagslug")

product_patterns = [
    path("", views.product_list, name="products"),
    path("<wagslug:slug>/", views.wt_product_serve, name="products.product"),
    path("<wagslug:slug>", views.wt_product_serve, name="products.product"),  # No trailing slash
    path("<slug>/", views.product_landing, name="products.product"),
    path("<product_slug>/<topic_slug>/", views.document_listing, name="products.documents"),
    path(
        "<product_slug>/<topic_slug>/<subtopic_slug>/",
        views.document_listing,
        name="products.subtopics",
    ),
]

topic_patterns = [
    path("<topic_slug>/", views.document_listing, name="products.topic_documents"),
    path(
        "<topic_slug>/<slug>/",
        views.document_listing,
        name="products.topic_product_documents",
    ),
]

urlpatterns = [
    path("products/", include(product_patterns)),
    path("topics/", include(topic_patterns)),
]

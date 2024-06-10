from django import template
from kitsune.products.models import Product

register = template.Library()


# Advert snippets
@register.inclusion_tag("products/product_card.html", takes_context=True)
def product_cards(context):
    return {
        "product_cards": Product.objects.filter(visible=True),
        "request": context["request"],
    }

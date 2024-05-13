from django import template
import json

register = template.Library()


@register.filter(name="json")
def json_filter(value):
    return json.dumps(value)

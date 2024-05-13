from django import template
from kitsune.sumo.utils import webpack_static


register = template.Library()

register.simple_tag(webpack_static)


@register.simple_tag
def include_script(script_name):
    path = "entrypoints/" + script_name + ".html"
    t = template.loader.get_template(path)
    return t.render()

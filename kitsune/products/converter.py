from wagtail.models import Page


# Custom converter for Wagtail to see if a page
# is served by Wagtail or served by Django
class WagtailConverter:
    regex = "[a-zA-Z0-9_-]+"

    def to_python(self, value):
        if Page.objects.filter(slug=value).exists():
            return value
        raise ValueError

    def to_url(self, value):
        return value

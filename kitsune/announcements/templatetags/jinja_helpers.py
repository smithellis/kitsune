from django_jinja import library

from kitsune.announcements.models import Announcement


@library.global_function
def get_announcements(request, product_slug=None):
    user = request.user if request.user.is_authenticated else None

    if user:
        return Announcement.get_for_groups(user.groups.values_list("id", flat=True))
    if product_slug:
        return Announcement.get_for_product_slug(product_slug)
    return Announcement.get_site_wide()

"""Fairly generic tagging utilities headed toward a dedicated app"""

from kitsune.tags.models import SumoTag


def add_existing_tag(tag_name, tag_manager):
    """Add a tag that already exists to an object. Return the normalized name.

    Given a tag name and a TaggableManager, have the manager add the tag of
    that name. The tag is matched case-insensitively. If there is no such tag,
    raise SumoTag.DoesNotExist.

    Return the canonically cased name of the tag.

    """
    # TODO: Think about adding a new method to _TaggableManager upstream.
    tag = SumoTag.objects.get(name__iexact=tag_name)
    tag_manager.add(tag)
    return tag.name

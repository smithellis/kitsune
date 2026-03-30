from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from kitsune.wiki.models import Document


@receiver(
    m2m_changed,
    sender=Document.restrict_to_groups.through,
    dispatch_uid="wiki.render_on_restrict_to_groups_change",
)
def render_on_restrict_to_groups_change(sender, instance, action, **kwargs):
    """
    Trigger a cascade re-render when a document's "restrict_to_groups" changes,
    since the parser uses "restrict_to_groups" to enforce inclusion permission checks.
    Translations inherit their parent's restrict_to_groups, so they must be
    re-rendered as well.
    """
    if action not in ("post_add", "post_remove", "post_clear"):
        return

    from kitsune.wiki.tasks import render_document_cascade

    render_document_cascade.delay(instance.id)
    for translation in instance.translations.all():
        render_document_cascade.delay(translation.id)


@receiver(
    post_save,
    sender=Document,
    dispatch_uid="wiki.reject_obsolete_translations",
)
def reject_obsolete_translations(sender, instance, created, **kwargs):
    """
    When a document is updated, reject any of its unreviewed machine translations
    that may have become obsolete.
    """
    if created:
        # A freshly created document can't lead to obsolete translations.
        return

    from kitsune.wiki.services import HybridTranslationService

    HybridTranslationService().reject_obsolete_translations(instance)

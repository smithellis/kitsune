from django.db import models
from django.db.models import Exists, OuterRef, Q

from kitsune.wiki.permissions import can_delete_documents_or_review_revisions


class VisibilityManager(models.Manager):
    """Abstract base class for the Document and Revision Managers."""

    # For managers of models related to documents, provide the name of the model attribute
    # that provides the related document. For example, for the manager of revisions, this
    # should be "document".
    document_relation: str | None = None

    @property
    def document_relation_prefix(self):
        return f"{self.document_relation}__" if self.document_relation else ""

    def get_creator_condition(self, user):
        """
        Return a conditional (e.g., a Q or Exists object) that is only true
        when the given user is the creator of this document or revision.
        """
        raise NotImplementedError

    def unrestricted(self, user, **kwargs):
        """
        Documents are unrestricted for a given user if they're not restricted
        to staff or a specific group, or when the user is staff/superuser and
        they're restricted by staff, or when the user is a member of the specific
        group to which they're restricted. A translation (i.e., a document with
        a parent), follows its parent's restrictions.
        """
        prefix = self.document_relation_prefix

        def unrestricted_condition(parent_prefix=""):
            """
            Create the unrestricted condition for either the document or
            the document's parent.
            """
            restrict_to_staff = f"{prefix}{parent_prefix}restrict_to_staff"
            restrict_to_group = f"{prefix}{parent_prefix}restrict_to_group"

            parent_condition = Q(**{f"{prefix}parent__isnull": not bool(parent_prefix)})
            not_restricted = Q(**{restrict_to_staff: False}) & Q(
                **{f"{restrict_to_group}__isnull": True}
            )
            staff_condition_fulfilled = Q(**{restrict_to_staff: True}) & Q(
                **{restrict_to_staff: user.is_superuser or user.is_staff}
            )
            group_condition_fulfilled = Q(**{f"{restrict_to_group}__isnull": False}) & Q(
                **{f"{restrict_to_group}__in": list(user.groups.values_list("id", flat=True))}
            )

            return parent_condition & (
                not_restricted | staff_condition_fulfilled | group_condition_fulfilled
            )

        return self.filter(
            unrestricted_condition() | unrestricted_condition("parent__"),
            **kwargs,
        )

    def visible(self, user, **kwargs):
        """
        Documents are effectively invisible when they have no approved content,
        and the given user is not a superuser, nor allowed to delete documents or
        review revisions, nor a creator of one of the (yet unapproved) revisions.
        """
        prefix = self.document_relation_prefix

        locale = kwargs.get(f"{prefix}locale")

        qs = self.unrestricted(user, **kwargs)

        if not user.is_authenticated:
            # Anonymous users only see documents with approved content.
            return qs.filter(**{f"{prefix}current_revision__isnull": False})

        if not (
            user.is_superuser or can_delete_documents_or_review_revisions(user, locale=locale)
        ):
            # Authenticated users without permission to see documents that
            # have no approved content, can only see those they have created.
            return qs.filter(
                Q(**{f"{prefix}current_revision__isnull": False})
                | self.get_creator_condition(user)
            )

        return qs

    def get_visible(self, user, **kwargs):
        return self.visible(user, **kwargs).get()


class DocumentManager(VisibilityManager):
    """The manager for the Document model."""

    def get_creator_condition(self, user):
        from kitsune.wiki.models import Revision

        return Exists(Revision.objects.filter(document=OuterRef("pk"), creator=user))


class RevisionManager(VisibilityManager):
    """The manager for the Revision model."""

    document_relation = "document"

    def get_creator_condition(self, user):
        return Q(creator=user)

"""
Signal handlers for tracking contribution events.

This module connects Django signals to automatically create immutable
ContributionEvent records when users contribute content. These events
form the basis for time-based metrics that remain accurate even when
content is deleted.
"""
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from kitsune.questions.models import Answer, AnswerVote, Question
from kitsune.users.models import ContributionEvent
from kitsune.wiki.models import Revision


@receiver(post_save, sender=Question)
def log_question_created(sender, instance, created, **kwargs):
    """Log when a new question is created (non-spam only)."""
    if (created and
        not instance.is_spam and
        instance.creator and
        hasattr(instance.creator, 'profile') and
        not instance.creator.profile.is_system_account):

        ContributionEvent.objects.create(
            user=instance.creator,
            contribution_type=ContributionEvent.ContributionType.QUESTION,
            content_type=ContentType.objects.get_for_model(Question),
            object_id=instance.id
        )


@receiver(post_save, sender=Answer)
def log_answer_created(sender, instance, created, **kwargs):
    """Log when a new answer is created (non-spam only)."""
    if (created and
        not instance.is_spam and
        instance.creator and
        hasattr(instance.creator, 'profile') and
        not instance.creator.profile.is_system_account):

        ContributionEvent.objects.create(
            user=instance.creator,
            contribution_type=ContributionEvent.ContributionType.ANSWER,
            content_type=ContentType.objects.get_for_model(Answer),
            object_id=instance.id
        )


@receiver(pre_save, sender=Answer)
def log_solution_marked(sender, instance, **kwargs):
    """Log when an answer is marked as a solution for the first time."""
    if instance.pk:
        try:
            old_instance = Answer.objects.get(pk=instance.pk)
            # Check if this answer is being marked as solution for the first time
            if (not old_instance.question.solution and
                instance.question.solution == instance and
                not instance.is_spam and
                instance.creator and
                hasattr(instance.creator, 'profile') and
                not instance.creator.profile.is_system_account):

                ContributionEvent.objects.create(
                    user=instance.creator,
                    contribution_type=ContributionEvent.ContributionType.SOLUTION,
                    content_type=ContentType.objects.get_for_model(Answer),
                    object_id=instance.id
                )
        except Answer.DoesNotExist:
            pass


@receiver(post_save, sender=Revision)
def log_kb_contribution(sender, instance, created, **kwargs):
    """Log KB edits and reviews."""
    # Log KB edit when revision is created
    if (created and
        instance.creator and
        hasattr(instance.creator, 'profile') and
        not instance.creator.profile.is_system_account):

        ContributionEvent.objects.create(
            user=instance.creator,
            contribution_type=ContributionEvent.ContributionType.KB_EDIT,
            content_type=ContentType.objects.get_for_model(Revision),
            object_id=instance.id,
            locale=instance.document.locale
        )

    # Log KB review when reviewer is set for the first time
    if (not created and
        instance.reviewer and
        hasattr(instance.reviewer, 'profile') and
        not instance.reviewer.profile.is_system_account):

        try:
            # Check if this is the first time reviewer is being set
            old_instance = Revision.objects.get(pk=instance.pk)
            if not old_instance.reviewer and instance.reviewer:
                ContributionEvent.objects.create(
                    user=instance.reviewer,
                    contribution_type=ContributionEvent.ContributionType.KB_REVIEW,
                    content_type=ContentType.objects.get_for_model(Revision),
                    object_id=instance.id,
                    locale=instance.document.locale
                )
        except Revision.DoesNotExist:
            pass


@receiver(post_save, sender=AnswerVote)
def log_helpful_vote(sender, instance, created, **kwargs):
    """Log when an answer receives a helpful vote."""
    if (created and
        instance.helpful and
        instance.answer and
        instance.answer.creator and
        not instance.answer.is_spam and
        hasattr(instance.answer.creator, 'profile') and
        not instance.answer.creator.profile.is_system_account):

        ContributionEvent.objects.create(
            user=instance.answer.creator,
            contribution_type=ContributionEvent.ContributionType.HELPFUL_VOTE,
            content_type=ContentType.objects.get_for_model(AnswerVote),
            object_id=instance.id
        )

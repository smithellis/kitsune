"""
Utility functions for calculating contribution statistics from the immutable event log.

These functions provide alternatives to the existing contribution counting methods
that use the ContributionEvent log instead of live database queries, ensuring
statistics remain accurate even when content is deleted.
"""
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from kitsune.users.models import ContributionEvent


def num_questions_from_events(user, since=None):
    """Return the number of questions a user has created from event log."""
    queryset = ContributionEvent.objects.filter(
        user=user,
        contribution_type=ContributionEvent.ContributionType.QUESTION
    )
    if since:
        queryset = queryset.filter(created_at__gte=since)
    return queryset.count()


def num_answers_from_events(user, since=None):
    """Return the number of answers a user has created from event log."""
    queryset = ContributionEvent.objects.filter(
        user=user,
        contribution_type=ContributionEvent.ContributionType.ANSWER
    )
    if since:
        queryset = queryset.filter(created_at__gte=since)
    return queryset.count()


def num_solutions_from_events(user, since=None):
    """Return the number of solutions a user has from event log."""
    queryset = ContributionEvent.objects.filter(
        user=user,
        contribution_type=ContributionEvent.ContributionType.SOLUTION
    )
    if since:
        queryset = queryset.filter(created_at__gte=since)
    return queryset.count()


def num_kb_edits_from_events(user, since=None, locale=None):
    """Return the number of KB edits a user has made from event log."""
    queryset = ContributionEvent.objects.filter(
        user=user,
        contribution_type=ContributionEvent.ContributionType.KB_EDIT
    )
    if since:
        queryset = queryset.filter(created_at__gte=since)
    if locale:
        queryset = queryset.filter(locale=locale)
    return queryset.count()


def num_kb_reviews_from_events(user, since=None, locale=None):
    """Return the number of KB reviews a user has done from event log."""
    queryset = ContributionEvent.objects.filter(
        user=user,
        contribution_type=ContributionEvent.ContributionType.KB_REVIEW
    )
    if since:
        queryset = queryset.filter(created_at__gte=since)
    if locale:
        queryset = queryset.filter(locale=locale)
    return queryset.count()


def num_helpful_votes_from_events(user, since=None):
    """Return the number of helpful votes a user has received from event log."""
    queryset = ContributionEvent.objects.filter(
        user=user,
        contribution_type=ContributionEvent.ContributionType.HELPFUL_VOTE
    )
    if since:
        queryset = queryset.filter(created_at__gte=since)
    return queryset.count()


def get_support_forum_contributors_from_events(start_date, end_date, min_answers=10):
    """
    Get count of support forum contributors from event log.

    Replaces the KPI calculation for support forum contributors.
    Returns count of users with at least min_answers answers in the date range,
    excluding answers to their own questions.
    """
    # Get users with enough answers in the time period
    contributors = (
        ContributionEvent.objects
        .filter(
            contribution_type=ContributionEvent.ContributionType.ANSWER,
            created_at__gte=start_date,
            created_at__lt=end_date
        )
        .values('user')
        .annotate(count=Count('user'))
        .filter(count__gte=min_answers)
    )

    return contributors.count()


def get_kb_contributors_from_events(start_date, end_date, locale=None):
    """
    Get KB contributors from event log.

    Replaces the KPI calculation for KB contributors.
    Returns count of unique users who edited or reviewed KB content in the date range.
    """
    # Get unique users who edited or reviewed in the time period
    queryset = ContributionEvent.objects.filter(
        contribution_type__in=[
            ContributionEvent.ContributionType.KB_EDIT,
            ContributionEvent.ContributionType.KB_REVIEW
        ],
        created_at__gte=start_date,
        created_at__lt=end_date
    )

    if locale:
        queryset = queryset.filter(locale=locale)

    return queryset.values('user').distinct().count()


def get_top_contributors_answers_from_events(start_date=None, end_date=None, limit=20):
    """
    Get top answer contributors from event log for leaderboards.

    Replaces the community leaderboard calculation for top answer contributors.
    Returns list of users with their answer counts in the specified time period.
    """
    if not start_date:
        start_date = timezone.now() - timedelta(days=90)
    if not end_date:
        end_date = timezone.now()

    contributors = (
        ContributionEvent.objects
        .filter(
            contribution_type=ContributionEvent.ContributionType.ANSWER,
            created_at__gte=start_date,
            created_at__lt=end_date
        )
        .values('user')
        .annotate(count=Count('user'))
        .order_by('-count')[:limit]
    )

    return list(contributors)


def get_top_contributors_kb_from_events(start_date=None, end_date=None, locale=None, limit=20):
    """
    Get top KB contributors from event log for leaderboards.

    Replaces the community leaderboard calculation for top KB contributors.
    Returns list of users with their KB contribution counts in the specified time period.
    """
    if not start_date:
        start_date = timezone.now() - timedelta(days=90)
    if not end_date:
        end_date = timezone.now()

    queryset = ContributionEvent.objects.filter(
        contribution_type__in=[
            ContributionEvent.ContributionType.KB_EDIT,
            ContributionEvent.ContributionType.KB_REVIEW
        ],
        created_at__gte=start_date,
        created_at__lt=end_date
    )

    if locale:
        queryset = queryset.filter(locale=locale)

    contributors = (
        queryset
        .values('user')
        .annotate(count=Count('user'))
        .order_by('-count')[:limit]
    )

    return list(contributors)

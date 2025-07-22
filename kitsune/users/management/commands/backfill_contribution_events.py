"""
Management command to backfill contribution events for existing content.

This command analyzes existing content in the database and creates
ContributionEvent records for all historical contributions, enabling
the immutable contribution tracking system to work with existing data.
"""
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction

from kitsune.questions.models import Answer, AnswerVote, Question
from kitsune.users.models import ContributionEvent
from kitsune.wiki.models import Revision


class Command(BaseCommand):
    help = "Backfill contribution events for existing content"

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='Backfill events for a specific user ID',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=1000,
            help='Number of items to process in each batch (default: 1000)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without making changes',
        )
        parser.add_argument(
            '--content-type',
            choices=['questions', 'answers', 'solutions', 'kb_edits', 'kb_reviews', 'helpful_votes', 'all'],
            default='all',
            help='Type of content to backfill (default: all)',
        )

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.batch_size = options['batch_size']

        if self.dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes will be made'))

        content_type = options['content_type']
        user_id = options['user_id']

        if content_type == 'all':
            self.backfill_all_content_types(user_id)
        else:
            self.backfill_content_type(content_type, user_id)

    def backfill_all_content_types(self, user_id=None):
        """Backfill all content types."""
        content_types = ['questions', 'answers', 'solutions', 'kb_edits', 'kb_reviews', 'helpful_votes']

        for content_type in content_types:
            self.stdout.write(f'\n--- Backfilling {content_type} ---')
            self.backfill_content_type(content_type, user_id)

    def backfill_content_type(self, content_type, user_id=None):
        """Backfill events for a specific content type."""
        if content_type == 'questions':
            self.backfill_questions(user_id)
        elif content_type == 'answers':
            self.backfill_answers(user_id)
        elif content_type == 'solutions':
            self.backfill_solutions(user_id)
        elif content_type == 'kb_edits':
            self.backfill_kb_edits(user_id)
        elif content_type == 'kb_reviews':
            self.backfill_kb_reviews(user_id)
        elif content_type == 'helpful_votes':
            self.backfill_helpful_votes(user_id)

    def backfill_questions(self, user_id=None):
        """Backfill question creation events."""
        queryset = Question.objects.filter(is_spam=False).exclude(
            creator__profile__account_type='system'
        ).select_related('creator', 'creator__profile')

        if user_id:
            queryset = queryset.filter(creator_id=user_id)

        total = queryset.count()
        self.stdout.write(f'Found {total} questions to process')

        if self.dry_run:
            return

        question_ct = ContentType.objects.get_for_model(Question)
        processed = 0
        created = 0

        for i in range(0, total, self.batch_size):
            batch = queryset[i:i + self.batch_size]
            events_to_create = []

            for question in batch:
                # Check if event already exists
                if not ContributionEvent.objects.filter(
                    user=question.creator,
                    contribution_type=ContributionEvent.ContributionType.QUESTION,
                    content_type=question_ct,
                    object_id=question.id
                ).exists():
                    events_to_create.append(ContributionEvent(
                        user=question.creator,
                        contribution_type=ContributionEvent.ContributionType.QUESTION,
                        content_type=question_ct,
                        object_id=question.id,
                        created_at=question.created
                    ))
                processed += 1

            if events_to_create:
                with transaction.atomic():
                    ContributionEvent.objects.bulk_create(events_to_create)
                    created += len(events_to_create)

            if processed % 5000 == 0:
                self.stdout.write(f'Processed {processed}/{total} questions...')

        self.stdout.write(self.style.SUCCESS(f'Questions: {created} events created'))

    def backfill_answers(self, user_id=None):
        """Backfill answer creation events."""
        queryset = Answer.objects.filter(is_spam=False).exclude(
            creator__profile__account_type='system'
        ).select_related('creator', 'creator__profile')

        if user_id:
            queryset = queryset.filter(creator_id=user_id)

        total = queryset.count()
        self.stdout.write(f'Found {total} answers to process')

        if self.dry_run:
            return

        answer_ct = ContentType.objects.get_for_model(Answer)
        processed = 0
        created = 0

        for i in range(0, total, self.batch_size):
            batch = queryset[i:i + self.batch_size]
            events_to_create = []

            for answer in batch:
                # Check if event already exists
                if not ContributionEvent.objects.filter(
                    user=answer.creator,
                    contribution_type=ContributionEvent.ContributionType.ANSWER,
                    content_type=answer_ct,
                    object_id=answer.id
                ).exists():
                    events_to_create.append(ContributionEvent(
                        user=answer.creator,
                        contribution_type=ContributionEvent.ContributionType.ANSWER,
                        content_type=answer_ct,
                        object_id=answer.id,
                        created_at=answer.created
                    ))
                processed += 1

            if events_to_create:
                with transaction.atomic():
                    ContributionEvent.objects.bulk_create(events_to_create)
                    created += len(events_to_create)

            if processed % 5000 == 0:
                self.stdout.write(f'Processed {processed}/{total} answers...')

        self.stdout.write(self.style.SUCCESS(f'Answers: {created} events created'))

    def backfill_solutions(self, user_id=None):
        """Backfill solution marking events."""
        queryset = Answer.objects.filter(
            is_spam=False,
            question__solution__isnull=False
        ).exclude(
            creator__profile__account_type='system'
        ).select_related('creator', 'creator__profile', 'question')

        if user_id:
            queryset = queryset.filter(creator_id=user_id)

        # Filter to only answers that are actually solutions
        solutions = []
        for answer in queryset:
            if answer.question.solution == answer:
                solutions.append(answer)

        total = len(solutions)
        self.stdout.write(f'Found {total} solutions to process')

        if self.dry_run:
            return

        answer_ct = ContentType.objects.get_for_model(Answer)
        processed = 0
        created = 0
        events_to_create = []

        for answer in solutions:
            # Check if event already exists
            if not ContributionEvent.objects.filter(
                user=answer.creator,
                contribution_type=ContributionEvent.ContributionType.SOLUTION,
                content_type=answer_ct,
                object_id=answer.id
            ).exists():
                events_to_create.append(ContributionEvent(
                    user=answer.creator,
                    contribution_type=ContributionEvent.ContributionType.SOLUTION,
                    content_type=answer_ct,
                    object_id=answer.id,
                    created_at=answer.created  # Use answer created date as approximation
                ))
            processed += 1

            if len(events_to_create) >= self.batch_size:
                with transaction.atomic():
                    ContributionEvent.objects.bulk_create(events_to_create)
                    created += len(events_to_create)
                    events_to_create = []

        # Process remaining events
        if events_to_create:
            with transaction.atomic():
                ContributionEvent.objects.bulk_create(events_to_create)
                created += len(events_to_create)

        self.stdout.write(self.style.SUCCESS(f'Solutions: {created} events created'))

    def backfill_kb_edits(self, user_id=None):
        """Backfill KB edit events."""
        queryset = Revision.objects.exclude(
            creator__profile__account_type='system'
        ).select_related('creator', 'creator__profile', 'document')

        if user_id:
            queryset = queryset.filter(creator_id=user_id)

        total = queryset.count()
        self.stdout.write(f'Found {total} KB edits to process')

        if self.dry_run:
            return

        revision_ct = ContentType.objects.get_for_model(Revision)
        processed = 0
        created = 0

        for i in range(0, total, self.batch_size):
            batch = queryset[i:i + self.batch_size]
            events_to_create = []

            for revision in batch:
                # Check if event already exists
                if not ContributionEvent.objects.filter(
                    user=revision.creator,
                    contribution_type=ContributionEvent.ContributionType.KB_EDIT,
                    content_type=revision_ct,
                    object_id=revision.id
                ).exists():
                    events_to_create.append(ContributionEvent(
                        user=revision.creator,
                        contribution_type=ContributionEvent.ContributionType.KB_EDIT,
                        content_type=revision_ct,
                        object_id=revision.id,
                        created_at=revision.created,
                        locale=revision.document.locale
                    ))
                processed += 1

            if events_to_create:
                with transaction.atomic():
                    ContributionEvent.objects.bulk_create(events_to_create)
                    created += len(events_to_create)

            if processed % 5000 == 0:
                self.stdout.write(f'Processed {processed}/{total} KB edits...')

        self.stdout.write(self.style.SUCCESS(f'KB edits: {created} events created'))

    def backfill_kb_reviews(self, user_id=None):
        """Backfill KB review events."""
        queryset = Revision.objects.filter(
            reviewer__isnull=False
        ).exclude(
            reviewer__profile__account_type='system'
        ).select_related('reviewer', 'reviewer__profile', 'document')

        if user_id:
            queryset = queryset.filter(reviewer_id=user_id)

        total = queryset.count()
        self.stdout.write(f'Found {total} KB reviews to process')

        if self.dry_run:
            return

        revision_ct = ContentType.objects.get_for_model(Revision)
        processed = 0
        created = 0

        for i in range(0, total, self.batch_size):
            batch = queryset[i:i + self.batch_size]
            events_to_create = []

            for revision in batch:
                # Check if event already exists
                if not ContributionEvent.objects.filter(
                    user=revision.reviewer,
                    contribution_type=ContributionEvent.ContributionType.KB_REVIEW,
                    content_type=revision_ct,
                    object_id=revision.id
                ).exists():
                    events_to_create.append(ContributionEvent(
                        user=revision.reviewer,
                        contribution_type=ContributionEvent.ContributionType.KB_REVIEW,
                        content_type=revision_ct,
                        object_id=revision.id,
                        created_at=revision.reviewed or revision.created,
                        locale=revision.document.locale
                    ))
                processed += 1

            if events_to_create:
                with transaction.atomic():
                    ContributionEvent.objects.bulk_create(events_to_create)
                    created += len(events_to_create)

            if processed % 5000 == 0:
                self.stdout.write(f'Processed {processed}/{total} KB reviews...')

        self.stdout.write(self.style.SUCCESS(f'KB reviews: {created} events created'))

    def backfill_helpful_votes(self, user_id=None):
        """Backfill helpful vote events."""
        queryset = AnswerVote.objects.filter(
            helpful=True,
            answer__is_spam=False
        ).exclude(
            answer__creator__profile__account_type='system'
        ).select_related('answer__creator', 'answer__creator__profile')

        if user_id:
            queryset = queryset.filter(answer__creator_id=user_id)

        total = queryset.count()
        self.stdout.write(f'Found {total} helpful votes to process')

        if self.dry_run:
            return

        vote_ct = ContentType.objects.get_for_model(AnswerVote)
        processed = 0
        created = 0

        for i in range(0, total, self.batch_size):
            batch = queryset[i:i + self.batch_size]
            events_to_create = []

            for vote in batch:
                # Check if event already exists
                if not ContributionEvent.objects.filter(
                    user=vote.answer.creator,
                    contribution_type=ContributionEvent.ContributionType.HELPFUL_VOTE,
                    content_type=vote_ct,
                    object_id=vote.id
                ).exists():
                    events_to_create.append(ContributionEvent(
                        user=vote.answer.creator,
                        contribution_type=ContributionEvent.ContributionType.HELPFUL_VOTE,
                        content_type=vote_ct,
                        object_id=vote.id,
                        created_at=vote.created
                    ))
                processed += 1

            if events_to_create:
                with transaction.atomic():
                    ContributionEvent.objects.bulk_create(events_to_create)
                    created += len(events_to_create)

            if processed % 5000 == 0:
                self.stdout.write(f'Processed {processed}/{total} helpful votes...')

        self.stdout.write(self.style.SUCCESS(f'Helpful votes: {created} events created'))

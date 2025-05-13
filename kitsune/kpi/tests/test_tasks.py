from datetime import datetime, timedelta
from unittest.mock import patch

import kitsune.kpi.management.utils
from kitsune.kpi.models import (
    CONTRIBUTOR_COHORT_CODE,
    KB_ENUS_CONTRIBUTOR_COHORT_CODE,
    KB_L10N_CONTRIBUTOR_COHORT_CODE,
    L10N_METRIC_CODE,
    SUPPORT_FORUM_HELPER_COHORT_CODE,
    Cohort,
    Metric,
)
from kitsune.kpi.tests import MetricKindFactory
from kitsune.questions.tests import AnswerFactory
from kitsune.sumo.tests import TestCase
from kitsune.users.tests import UserFactory
from kitsune.wiki.config import MAJOR_SIGNIFICANCE, MEDIUM_SIGNIFICANCE, TYPO_SIGNIFICANCE
from kitsune.wiki.tests import ApprovedRevisionFactory, DocumentFactory
from kitsune.tasks import cohort_analysis, update_l10n_metric


class CohortAnalysisTasksTests(TestCase):
    def setUp(self):
        today = datetime.today()
        self.start_of_first_week = today - timedelta(days=today.weekday(), weeks=12)

        revisions = ApprovedRevisionFactory.create_batch(3, created=self.start_of_first_week)

        reviewer = UserFactory()
        ApprovedRevisionFactory(reviewer=reviewer, created=self.start_of_first_week)

        ApprovedRevisionFactory(
            creator=revisions[1].creator,
            reviewer=reviewer,
            created=self.start_of_first_week + timedelta(weeks=1, days=2),
        )
        ApprovedRevisionFactory(created=self.start_of_first_week + timedelta(weeks=1, days=1))

        for r in revisions:
            lr = ApprovedRevisionFactory(
                created=self.start_of_first_week + timedelta(days=1), document__locale="es"
            )
            ApprovedRevisionFactory(
                created=self.start_of_first_week + timedelta(weeks=2, days=1),
                creator=lr.creator,
                document__locale="es",
            )

        answers = AnswerFactory.create_batch(
            7, created=self.start_of_first_week + timedelta(weeks=1, days=2)
        )

        AnswerFactory(
            question=answers[2].question,
            creator=answers[2].question.creator,
            created=self.start_of_first_week + timedelta(weeks=1, days=2),
        )

        for a in answers[:2]:
            AnswerFactory(
                creator=a.creator, created=self.start_of_first_week + timedelta(weeks=2, days=5)
            )

        # Call the Celery task directly
        cohort_analysis()

    def test_contributor_cohort_analysis(self):
        c1 = Cohort.objects.get(kind__code=CONTRIBUTOR_COHORT_CODE, start=self.start_of_first_week)
        self.assertEqual(c1.size, 8)

        c1r1 = c1.retention_metrics.get(start=self.start_of_first_week + timedelta(weeks=1))
        self.assertEqual(c1r1.size, 2)

        c1r2 = c1.retention_metrics.get(start=self.start_of_first_week + timedelta(weeks=2))
        self.assertEqual(c1r2.size, 3)

        c2 = Cohort.objects.get(
            kind__code=CONTRIBUTOR_COHORT_CODE, start=self.start_of_first_week + timedelta(weeks=1)
        )
        self.assertEqual(c2.size, 8)

        c2r1 = c2.retention_metrics.get(start=self.start_of_first_week + timedelta(weeks=2))

        self.assertEqual(c2r1.size, 2)

    def test_kb_enus_contributor_cohort_analysis(self):
        c1 = Cohort.objects.get(
            kind__code=KB_ENUS_CONTRIBUTOR_COHORT_CODE, start=self.start_of_first_week
        )
        self.assertEqual(c1.size, 5)

        c1r1 = c1.retention_metrics.get(start=self.start_of_first_week + timedelta(weeks=1))
        self.assertEqual(c1r1.size, 2)

        c1r2 = c1.retention_metrics.get(start=self.start_of_first_week + timedelta(weeks=2))
        self.assertEqual(c1r2.size, 0)

        c2 = Cohort.objects.get(
            kind__code=KB_ENUS_CONTRIBUTOR_COHORT_CODE,
            start=self.start_of_first_week + timedelta(weeks=1),
        )
        self.assertEqual(c2.size, 1)

        c2r1 = c2.retention_metrics.get(start=self.start_of_first_week + timedelta(weeks=2))

        self.assertEqual(c2r1.size, 0)

    def test_kb_l10n_contributor_cohort_analysis(self):
        c1 = Cohort.objects.get(
            kind__code=KB_L10N_CONTRIBUTOR_COHORT_CODE, start=self.start_of_first_week
        )
        self.assertEqual(c1.size, 3)

        c1r1 = c1.retention_metrics.get(start=self.start_of_first_week + timedelta(weeks=1))
        self.assertEqual(c1r1.size, 0)

        c1r2 = c1.retention_metrics.get(start=self.start_of_first_week + timedelta(weeks=2))
        self.assertEqual(c1r2.size, 3)

        c2 = Cohort.objects.get(
            kind__code=KB_L10N_CONTRIBUTOR_COHORT_CODE,
            start=self.start_of_first_week + timedelta(weeks=1),
        )
        self.assertEqual(c2.size, 0)

        c2r1 = c2.retention_metrics.get(start=self.start_of_first_week + timedelta(weeks=2))

        self.assertEqual(c2r1.size, 0)

    def test_support_forum_helper_cohort_analysis(self):
        c1 = Cohort.objects.get(
            kind__code=SUPPORT_FORUM_HELPER_COHORT_CODE, start=self.start_of_first_week
        )
        self.assertEqual(c1.size, 0)

        c1r1 = c1.retention_metrics.get(start=self.start_of_first_week + timedelta(weeks=1))
        self.assertEqual(c1r1.size, 0)

        c2 = Cohort.objects.get(
            kind__code=SUPPORT_FORUM_HELPER_COHORT_CODE,
            start=self.start_of_first_week + timedelta(weeks=1),
        )
        self.assertEqual(c2.size, 7)

        c2r1 = c2.retention_metrics.get(start=self.start_of_first_week + timedelta(weeks=2))

        self.assertEqual(c2r1.size, 2)


class L10nMetricTaskTests(TestCase):
    @patch.object(kitsune.sumo.googleanalytics, "visitors_by_locale")
    @patch.object(kitsune.kpi.management.utils, "_get_top_docs")
    def test_update_l10n_metric_task(self, _get_top_docs, visitors_by_locale):
        l10n_kind = MetricKindFactory(code=L10N_METRIC_CODE)

        # Create the en-US document with an approved revision.
        doc = DocumentFactory()
        rev = ApprovedRevisionFactory(
            document=doc, significance=MEDIUM_SIGNIFICANCE, is_ready_for_localization=True
        )

        # Create an es translation that is up to date.
        es_doc = DocumentFactory(parent=doc, locale="es")
        ApprovedRevisionFactory(document=es_doc, based_on=rev)

        # Create a de translation without revisions.
        DocumentFactory(parent=doc, locale="de")

        # Mock some calls.
        visitors_by_locale.return_value = {
            "en-US": 50,
            "de": 20,
            "es": 25,
            "fr": 5,
        }
        _get_top_docs.return_value = [doc]

        # Call the Celery task directly
        update_l10n_metric()
        metrics = Metric.objects.filter(kind=l10n_kind)
        self.assertEqual(1, len(metrics))
        self.assertEqual(75, metrics[0].value)

        # Create a new revision with TYPO_SIGNIFICANCE. It shouldn't
        # affect the results.
        ApprovedRevisionFactory(
            document=doc, significance=TYPO_SIGNIFICANCE, is_ready_for_localization=True
        )
        Metric.objects.all().delete()
        update_l10n_metric()
        metrics = Metric.objects.filter(kind=l10n_kind)
        self.assertEqual(1, len(metrics))
        self.assertEqual(75, metrics[0].value)

        # Create a new revision with MEDIUM_SIGNIFICANCE. The coverage
        # should now be 62% (0.5/1 * 25/100 + 1/1 * 50/100)
        m1 = ApprovedRevisionFactory(
            document=doc, significance=MEDIUM_SIGNIFICANCE, is_ready_for_localization=True
        )
        Metric.objects.all().delete()
        update_l10n_metric()
        metrics = Metric.objects.filter(kind=l10n_kind)
        self.assertEqual(1, len(metrics))
        self.assertEqual(62, metrics[0].value)

        # And another new revision with MEDIUM_SIGNIFICANCE makes the
        # coverage 50% (1/1 * 50/100).
        m2 = ApprovedRevisionFactory(
            document=doc, significance=MEDIUM_SIGNIFICANCE, is_ready_for_localization=True
        )
        Metric.objects.all().delete()
        update_l10n_metric()
        metrics = Metric.objects.filter(kind=l10n_kind)
        self.assertEqual(1, len(metrics))
        self.assertEqual(50, metrics[0].value)

        # If we remove the two MEDIUM_SIGNIFICANCE revisions and add a
        # MAJOR_SIGNIFICANCE revision, the coverage is 50% as well.
        ApprovedRevisionFactory(
            document=doc, significance=MAJOR_SIGNIFICANCE, is_ready_for_localization=True
        )
        m1.delete()
        m2.delete()
        Metric.objects.all().delete()
        update_l10n_metric()
        metrics = Metric.objects.filter(kind=l10n_kind)
        self.assertEqual(1, len(metrics))
        self.assertEqual(50, metrics[0].value)

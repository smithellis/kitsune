from django.conf import settings
from django.test import TestCase
from kitsune.celery import app as celery_app
from unittest import mock


class TestCeleryBeatSchedule(TestCase):
    def test_all_scheduled_tasks_registered(self):
        # All scheduled tasks in CELERY_BEAT_SCHEDULE should be registered in Celery
        schedule = settings.CELERY_BEAT_SCHEDULE
        for name, entry in schedule.items():
            task_name = entry["task"] if isinstance(entry, dict) else entry.task
            self.assertIn(
                task_name, celery_app.tasks, f"Task '{task_name}' not registered in Celery app."
            )

    def test_schedule_entries_match(self):
        # Ensure the schedule entries are present and have expected keys
        schedule = settings.CELERY_BEAT_SCHEDULE
        for name, entry in schedule.items():
            self.assertIn("task", entry, f"Schedule entry '{name}' missing 'task' key.")
            self.assertIn("schedule", entry, f"Schedule entry '{name}' missing 'schedule' key.")

    def test_tasks_can_be_called(self):
        # Try calling each task with a mock to ensure no import errors
        schedule = settings.CELERY_BEAT_SCHEDULE
        for name, entry in schedule.items():
            task_name = entry["task"]
            if task_name in celery_app.tasks:
                task = celery_app.tasks[task_name]
                with mock.patch.object(task, "run", return_value=None) as mocked_run:
                    task.apply(args=entry.get("args", []), kwargs=entry.get("kwargs", {}))
                    mocked_run.assert_called()

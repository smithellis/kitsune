from unittest.mock import call, patch

from django.test import TestCase

from kitsune.users.tests import GroupFactory
from kitsune.wiki.tests import DocumentFactory


class RenderOnRestrictToGroupsChangeTests(TestCase):
    @patch("kitsune.wiki.tasks.render_document_cascade")
    def test_adding_group_triggers_render_cascade(self, mock_task):
        doc = DocumentFactory()
        group = GroupFactory()
        doc.restrict_to_groups.add(group)
        mock_task.delay.assert_called_once_with(doc.id)

    @patch("kitsune.wiki.tasks.render_document_cascade")
    def test_removing_group_triggers_render_cascade(self, mock_task):
        doc = DocumentFactory()
        group = GroupFactory()
        doc.restrict_to_groups.add(group)
        mock_task.delay.reset_mock()

        doc.restrict_to_groups.remove(group)
        mock_task.delay.assert_called_once_with(doc.id)

    @patch("kitsune.wiki.tasks.render_document_cascade")
    def test_clearing_groups_triggers_render_cascade(self, mock_task):
        doc = DocumentFactory()
        group = GroupFactory()
        doc.restrict_to_groups.add(group)
        mock_task.delay.reset_mock()

        doc.restrict_to_groups.clear()
        mock_task.delay.assert_called_once_with(doc.id)

    @patch("kitsune.wiki.tasks.render_document_cascade")
    def test_setting_groups_triggers_render_cascade(self, mock_task):
        doc = DocumentFactory()
        group1 = GroupFactory()
        group2 = GroupFactory()
        doc.restrict_to_groups.set([group1, group2])
        mock_task.delay.assert_called_once_with(doc.id)

    @patch("kitsune.wiki.tasks.render_document_cascade")
    def test_translations_are_re_rendered(self, mock_task):
        parent = DocumentFactory()
        translation = DocumentFactory(parent=parent, locale="de")
        group = GroupFactory()
        mock_task.delay.reset_mock()

        parent.restrict_to_groups.add(group)
        mock_task.delay.assert_has_calls(
            [call(parent.id), call(translation.id)],
            any_order=True,
        )
        assert mock_task.delay.call_count == 2

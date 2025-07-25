import re
from unittest import mock

from django.contrib.sites.models import Site
from django.core import mail
from django.test.utils import override_settings

from kitsune.questions.events import QuestionReplyEvent, QuestionSolvedEvent
from kitsune.questions.models import Question
from kitsune.questions.tests import AnswerFactory, QuestionFactory
from kitsune.sumo.tests import TestCase, attrs_eq, post, starts_with
from kitsune.users.models import Setting
from kitsune.users.templatetags.jinja_helpers import display_name
from kitsune.users.tests import UserFactory

ANSWER_EMAIL_TO_ANONYMOUS = """{replier} commented on a Firefox question on \
testserver:

{title} (https://testserver/{locale}questions/{question_id}?utm_campaign=\
questions-reply&utm_source=notification&utm_medium=email)

{replier} wrote:
"{content}"

Avoid support scams. We will never ask you to call or text a phone number \
or share personal information. Learn more:
https://support.mozilla.org/kb/avoid-and-report-mozilla-tech-support-scams

See the comment:
https://testserver/{locale}questions/{question_id}?utm_campaign=\
questions-reply&utm_source=notification&utm_medium=email\
#answer-{answer_id}

Help other Firefox users by browsing for unsolved questions on testserver:
https://testserver/questions?filter=unsolved

You might just make someone's day!

--
Unsubscribe from these emails:
https://testserver/{locale}unsubscribe/"""

ANSWER_EMAIL = "Hi {to_user},\n\n" + ANSWER_EMAIL_TO_ANONYMOUS

ANSWER_EMAIL_TO_ASKER = """Hi {asker},

{replier} has posted an answer to your question on testserver:
{title} (https://testserver/{locale}questions/{question_id}?utm_campaign=\
questions-reply&utm_source=notification&utm_medium=email)

{replier} wrote:
"{content}"

Avoid support scams. We will never ask you to call or text a phone number \
or share personal information. Learn more:
https://support.mozilla.org/kb/avoid-and-report-mozilla-tech-support-scams

If this doesn't solve your problem, let {replier} know by replying on the \
website:
https://testserver/{locale}questions/{question_id}?utm_campaign=\
questions-reply&utm_source=notification&utm_medium=email\
#answer-{answer_id}

If this answer solves your problem, please mark it as "solved":"""

SOLUTION_EMAIL_TO_ANONYMOUS = """We just wanted to let you know that \
{replier} has found a solution to a Firefox question that you're following.

The question:
{title}

was marked as solved by its asker, {asker}.

You can view the solution using the link below.

Did this answer also help you? Did you find another post more helpful? Let \
other Firefox users know by voting next to the answer.

https://testserver/{locale}questions/{question_id}?utm_campaign=\
questions-solved&utm_source=notification&utm_medium=email#answer-{answer_id}

Did you know that {replier} is a Firefox user just like you? Get started \
helping other Firefox users by browsing questions at \
https://testserver/questions?filter=unsolved -- you might just make someone's \
day!

--
Unsubscribe from these emails:
https://testserver/{locale}unsubscribe/"""

SOLUTION_EMAIL = "Hi {to_user},\n\n" + SOLUTION_EMAIL_TO_ANONYMOUS


class NotificationsTests(TestCase):
    """Test that notifications get sent."""

    @mock.patch.object(QuestionReplyEvent, "fire")
    def test_fire_on_new_answer(self, fire):
        """The event fires when a new answer is saved."""
        q = QuestionFactory()
        AnswerFactory(question=q)

        assert fire.called

    @mock.patch.object(QuestionSolvedEvent, "fire")
    def test_fire_on_solution(self, fire):
        """The event also fires when an answer is marked as a solution."""
        a = AnswerFactory()
        q = a.question

        self.client.login(username=q.creator, password="testpass")
        post(self.client, "questions.solve", args=[q.id, a.id])

        assert fire.called

    def _toggle_watch_question(self, event_type, user, turn_on=True):
        """Helper to watch/unwatch a question. Fails if called twice with
        the same turn_on value."""
        q = QuestionFactory()

        self.client.login(username=user.username, password="testpass")

        event_cls = QuestionReplyEvent if event_type == "reply" else QuestionSolvedEvent
        # Make sure 'before' values are the reverse.
        if turn_on:
            assert not event_cls.is_notifying(user, q), "{} should not be notifying.".format(
                event_cls.__name__
            )
        else:
            assert event_cls.is_notifying(user, q), "{} should be notifying.".format(
                event_cls.__name__
            )

        url = "questions.watch" if turn_on else "questions.unwatch"
        data = {"event_type": event_type} if turn_on else {}
        post(self.client, url, data, args=[q.id])

        if turn_on:
            assert event_cls.is_notifying(user, q), "{} should be notifying.".format(
                event_cls.__name__
            )
        else:
            assert not event_cls.is_notifying(user, q), "{} should not be notifying.".format(
                event_cls.__name__
            )
        return q

    @mock.patch.object(Site.objects, "get_current")
    @override_settings(TIDINGS_CONFIRM_ANONYMOUS_WATCHES=False, STATIC_URL="https://example.com/")
    def test_solution_notification(self, get_current):
        """Assert that hitting the watch toggle toggles and that proper mails
        are sent to anonymous and registered watchers."""
        # TODO: Too monolithic. Split this test into several.
        get_current.return_value.domain = "testserver"

        u = UserFactory()
        q = self._toggle_watch_question("solution", u, turn_on=True)
        QuestionSolvedEvent.notify("anon@ymous.com", q)

        a = AnswerFactory(question=q)

        # Mark a solution
        self.client.login(username=q.creator.username, password="testpass")
        post(self.client, "questions.solve", args=[q.id, a.id])

        # Order of emails is not important.
        self.assertEqual(len(mail.outbox), 2)

        attrs_eq(
            mail.outbox[0],
            to=["anon@ymous.com"],
            subject="Solution found to Firefox Help question",
        )
        starts_with(
            mail.outbox[0].body,
            SOLUTION_EMAIL_TO_ANONYMOUS.format(
                replier=display_name(a.creator),
                title=q.title,
                asker=display_name(q.creator),
                question_id=q.id,
                answer_id=a.id,
                locale="en-US/",
            ),
        )

        attrs_eq(mail.outbox[1], to=[u.email], subject="Solution found to Firefox Help question")
        starts_with(
            mail.outbox[1].body,
            SOLUTION_EMAIL.format(
                to_user=display_name(u),
                replier=display_name(a.creator),
                title=q.title,
                asker=display_name(q.creator),
                question_id=q.id,
                answer_id=a.id,
                locale="en-US/",
            ),
        )

        # make sure email has the proper static url
        self.assertRegex(
            mail.outbox[1].alternatives[0][0],
            rf"{re.escape('https://example.com/mozilla-support.')}[0-9a-z]+\.png",
        )

    @mock.patch.object(Site.objects, "get_current")
    def test_autowatch_reply(self, get_current):
        """
        Tests the autowatch setting of users.

        If a user has the setting turned on, they should get
        notifications after posting in a thread for that thread. If they
        have that setting turned off, they should not.
        """

        get_current.return_value.domain = "testserver"

        u = UserFactory()
        t1 = QuestionFactory()
        t2 = QuestionFactory()
        assert not QuestionReplyEvent.is_notifying(u, t1)
        assert not QuestionReplyEvent.is_notifying(u, t2)

        self.client.login(username=u.username, password="testpass")
        s = Setting.objects.create(user=u, name="questions_watch_after_reply", value="True")
        data = {"content": "some content"}
        post(self.client, "questions.reply", data, args=[t1.id])
        assert QuestionReplyEvent.is_notifying(u, t1)

        s.value = "False"
        s.save()
        post(self.client, "questions.reply", data, args=[t2.id])
        assert not QuestionReplyEvent.is_notifying(u, t2)

    @mock.patch.object(Site.objects, "get_current")
    def test_solution_notification_deleted(self, get_current):
        """Calling QuestionSolvedEvent.fire() should not query the
        questions_question table.

        This test attempts to simulate the replication lag presumed to cause
        bug 585029.

        """
        get_current.return_value.domain = "testserver"

        a = AnswerFactory()
        q = a.question
        q.solution = a
        q.save()

        a_user = a.creator
        QuestionSolvedEvent.notify(a_user, q)
        event = QuestionSolvedEvent(a)

        # Delete the question, pretend it hasn't been replicated yet
        Question.objects.get(pk=q.pk).delete()

        event.fire(exclude=[q.creator])

        # Since we'll attempt to reconstruct the event within the Celery task, the answer
        # needed to reconstruct the event will no longer exist since it's been deleted
        # (cascade delete due to the deletion of the question). Therefore no emails will
        # be sent.
        self.assertEqual(len(mail.outbox), 0)


class TestAnswerNotifications(TestCase):
    """Assert that hitting the watch toggle toggles and that proper mails
    are sent to anonymous users, registered users, and the question
    asker."""

    def setUp(self):
        super().setUp()
        self._get_current_mock = mock.patch.object(Site.objects, "get_current")
        self._get_current_mock.start().return_value.domain = "testserver"
        self.question = QuestionFactory()
        QuestionReplyEvent.notify(self.question.creator, self.question)

    def tearDown(self):
        super().tearDown()
        self._get_current_mock.stop()

    def makeAnswer(self):
        self.answer = AnswerFactory(question=self.question)

    def format_args(self):
        return {
            "title": self.question.title,
            "content": self.answer.content,
            "replier": display_name(self.answer.creator),
            "question_id": self.question.id,
            "answer_id": self.answer.id,
            "locale": "en-US/",
            "asker": display_name(self.question.creator),
        }

    @override_settings(TIDINGS_CONFIRM_ANONYMOUS_WATCHES=False)
    def test_notify_anonymous(self):
        """Test that anonymous users are notified of new answers."""
        ANON_EMAIL = "anonymous@example.com"
        QuestionReplyEvent.notify(ANON_EMAIL, self.question)
        self.makeAnswer()

        # One for the asker's email, and one for the anonymous email.
        self.assertEqual(2, len(mail.outbox))
        notification = [m for m in mail.outbox if m.to == [ANON_EMAIL]][0]

        self.assertEqual([ANON_EMAIL], notification.to)
        self.assertEqual("Re: {}".format(self.question.title), notification.subject)

        body = re.sub(r"auth=[a-zA-Z0-9%_-]+", "auth=AUTH", notification.body)
        starts_with(body, ANSWER_EMAIL_TO_ANONYMOUS.format(**self.format_args()))

    def test_notify_arbitrary(self):
        """Test that arbitrary users are notified of new answers."""
        watcher = UserFactory()
        QuestionReplyEvent.notify(watcher, self.question)
        self.makeAnswer()

        # One for the asker's email, and one for the watcher's email.
        self.assertEqual(2, len(mail.outbox))
        notification = [m for m in mail.outbox if m.to == [watcher.email]][0]

        self.assertEqual([watcher.email], notification.to)
        self.assertEqual("Re: {}".format(self.question.title), notification.subject)

        body = re.sub(r"auth=[a-zA-Z0-9%_-]+", "auth=AUTH", notification.body)
        starts_with(body, ANSWER_EMAIL.format(to_user=display_name(watcher), **self.format_args()))

    def test_notify_asker(self):
        """Test that the answer is notified of answers, without registering."""
        self.makeAnswer()

        self.assertEqual(1, len(mail.outbox))
        notification = mail.outbox[0]

        self.assertEqual([self.question.creator.email], notification.to)
        self.assertEqual(
            '{} posted an answer to your question "{}"'.format(
                display_name(self.answer.creator), self.question.title
            ),
            notification.subject,
        )

        starts_with(notification.body, ANSWER_EMAIL_TO_ASKER.format(**self.format_args()))

    @override_settings(DEFAULT_REPLY_TO_EMAIL="replyto@example.com")
    def test_notify_anonymous_reply_to(self):
        """
        Test that notifications to the asker have a correct reply to field.
        """
        ANON_EMAIL = "anonymous@example.com"
        QuestionReplyEvent.notify(ANON_EMAIL, self.question)
        self.makeAnswer()

        notification = [m for m in mail.outbox if m.to == [ANON_EMAIL]][0]
        # Headers should be compared case-insensitively.
        headers = {k.lower(): v for k, v in list(notification.extra_headers.items())}
        self.assertEqual("replyto@example.com", headers["reply-to"])

    @override_settings(DEFAULT_REPLY_TO_EMAIL="replyto@example.com")
    def test_notify_arbitrary_reply_to(self):
        """
        Test that notifications to the asker have a correct reply to field.
        """
        watcher = UserFactory()
        QuestionReplyEvent.notify(watcher, self.question)
        self.makeAnswer()

        notification = [m for m in mail.outbox if m.to == [watcher.email]][0]
        # Headers should be compared case-insensitively.
        headers = {k.lower(): v for k, v in list(notification.extra_headers.items())}
        self.assertEqual("replyto@example.com", headers["reply-to"])

    @override_settings(DEFAULT_REPLY_TO_EMAIL="replyto@example.com")
    def test_notify_asker_reply_to(self):
        """
        Test that notifications to the asker have a correct reply to field.
        """
        self.makeAnswer()
        # Headers should be compared case-insensitively.
        headers = {k.lower(): v for k, v in list(mail.outbox[0].extra_headers.items())}
        self.assertEqual("replyto@example.com", headers["reply-to"])

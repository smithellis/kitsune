from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.core import mail

import mock
from nose.tools import eq_

from sumo.tests import TestCase
from sumo.urlresolvers import reverse
from users.models import RegistrationProfile


class RegisterTestCase(TestCase):
    fixtures = ['users.json']

    def setUp(self):
        self.old_debug = settings.DEBUG
        settings.DEBUG = True
        self.client.logout()

    def tearDown(self):
        settings.DEBUG = self.old_debug

    @mock.patch_object(Site.objects, 'get_current')
    def test_new_user(self, get_current):
        get_current.return_value.domain = 'su.mo.com'
        response = self.client.post(reverse('users.register', locale='en-US'),
                                    {'username': 'newbie',
                                     'email': 'newbie@example.com',
                                     'password1': 'foo',
                                     'password2': 'foo'}, follow=True)
        eq_(200, response.status_code)
        u = User.objects.get(username='newbie')
        assert u.password.startswith('sha256')
        assert not u.is_active
        eq_(1, len(mail.outbox))
        assert mail.outbox[0].subject.find('Please confirm your') == 0
        key = RegistrationProfile.objects.all()[0].activation_key
        assert mail.outbox[0].body.find('activate/%s' % key) > 0

    @mock.patch_object(Site.objects, 'get_current')
    def test_new_user_activation(self, get_current):
        get_current.return_value.domain = 'su.mo.com'
        user = RegistrationProfile.objects.create_inactive_user(
            'sumouser1234', 'testpass', 'sumouser@test.com')
        assert not user.is_active
        key = RegistrationProfile.objects.all()[0].activation_key
        url = reverse('users.activate', args=[key])
        response = self.client.get(url, follow=True)
        eq_(200, response.status_code)
        user = User.objects.get(pk=user.pk)
        assert user.is_active

    def test_duplicate_username(self):
        response = self.client.post(reverse('users.register', locale='en-US'),
                                    {'username': 'jsocol',
                                     'email': 'newbie@example.com',
                                     'password1': 'foo',
                                     'password2': 'foo'}, follow=True)
        self.assertContains(response, 'already exists')

    def test_duplicate_email(self):
        User.objects.create(username='noob', email='noob@example.com').save()
        response = self.client.post(reverse('users.register', locale='en-US'),
                                    {'username': 'newbie',
                                     'email': 'noob@example.com',
                                     'password1': 'foo',
                                     'password2': 'foo'}, follow=True)
        self.assertContains(response, 'already exists')

    def test_no_match_passwords(self):
        response = self.client.post(reverse('users.register', locale='en-US'),
                                    {'username': 'newbie',
                                     'email': 'newbie@example.com',
                                     'password1': 'foo',
                                     'password2': 'bar'}, follow=True)
        self.assertContains(response, 'must match')

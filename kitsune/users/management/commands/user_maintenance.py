from django.core.management.base import BaseCommand

from datetime import datetime, timedelta
from itertools import chain

from django.contrib.auth.models import User


class Command(BaseCommand):
    def handle(self, *args, **options):
        # Get users who:
        # * Are inactive and haven't logged in during the past year - an aren't superusers
        # * Have not migrated to FxA AKA Mozilla Accounts and aren't superusers
        # (Leaving out superusers because they are special and testing is no fun
        # when you delete your own account)
        inactive_users = User.objects.filter(
            is_active=False,
            last_login__lte=datetime.now() - timedelta(days=365),
            is_superuser=False,
        )
        non_fxa_migrated_users = User.objects.filter(
            profile__is_fxa_migrated=False, is_superuser=False
        )

        # If these users don't have revisions, questions, answers or threads
        # we delete them
        for user in chain(inactive_users, non_fxa_migrated_users):
            # Get all the content for the user
            revisions = user.created_revisions.all()
            questions = user.questions.all()
            wiki_threads = user.wiki_thread_set.all()
            answers = user.answers.all()
            print(user.username + "::", revisions, wiki_threads, questions, answers)
            # If there is no content owned/created by user, and they haven't logged in
            # during the past year, delete the user
            if not (revisions or questions or answers or wiki_threads):
                print(
                    "Deleting user: "
                    + user.username
                    + " - "
                    + user.email
                    + " - "
                    + str(user.last_login.date())
                )
                user.delete()
            # If they do have content, we are going to deactive them and
            # anonymize their accounts
            else:
                if not user.username.startswith("Inactive User"):
                    print(
                        "Deactivating and Anonymizing user: "
                        + user.username
                        + " - "
                        + user.email
                        + " - "
                        + str(user.last_login.date())
                    )
                    user.profile.clear()
                    user.profile.save()
                    user.is_active = False
                    user.is_staff = False
                    user.email = "user" + str(user.id) + "@example.com"
                    user.save()

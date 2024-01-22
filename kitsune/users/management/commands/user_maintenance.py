from django.core.management.base import BaseCommand

from datetime import datetime, timedelta
from itertools import chain

from django.contrib.auth.models import User
from kitsune.users.utils import anonymize_user


class Command(BaseCommand):
    help = """
    Deletes users who:
    1) Are inactive and haven't logged in during the past year, aren't superusers,
       and have no revisions or questions that are not archive
    2) Have not migrated to FxA AKA Mozilla Accounts, aren't superusers, and have
       no revisions or questions that are not archive
    Deactivates and anonymizes users who:
    1) Are inactive and haven't logged in during the past year, aren't superusers,
       and have revisions or questions that are not archived
    2) Have not migrated to FxA AKA Mozilla Accounts, aren't superusers, and have
       revisions or questions that are not archived
    """

    def handle(self, *args, **options):
        # Get users who:
        # * Are inactive and haven't logged in during the past year - and aren't superusers
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

        # If these users don't have revisions or questions that are not archived,
        # delete the user
        for user in chain(inactive_users, non_fxa_migrated_users):
            # Get all the non archived content for the user
            revisions = user.created_revisions.all().filter(document__is_archived=False)
            questions = user.questions.all().filter(is_archived=False)

            # If there is no live content owned/created
            # by user, delete them
            if not (revisions or questions):
                user.delete()
            # If they do have content, we are going to deactive them and
            # anonymize their accounts
            else:
                anonymize_user(user)  # this method also performs the deactivation

from datetime import datetime, timedelta
from itertools import chain

from django.contrib.auth.models import User

from kitsune.wiki.models import Revision
from kitsune.kbforums.models import Thread, Post
from kitsune.questions.models import Question, Answer

# Get users who are not active, and users who are not
# migrated to Mozilla Account
inactive_users = User.objects.filter(is_active=False)
non_fxa_migrated_users = User.objects.filter(profile__is_fxa_migrated=False)

# For any user who is not migrated, or who is not active,
# delete them if they have no content and have not logged in
# during the past year
for user in chain(inactive_users, non_fxa_migrated_users):
    # Get all the content for the user
    revisions = Revision.objects.filter(creator=user)
    threads = Thread.objects.filter(creator=user)
    posts = Post.objects.filter(creator=user)
    questions = Question.objects.filter(creator=user)
    answers = Answer.objects.filter(creator=user)

    # If there is no content owned/created by user, and they haven't logged in
    # during the past year, delete the user
    if not (revisions or threads or posts or questions or answers) and (
        user.last_login.date() < (datetime.now().date() - timedelta(days=365))
    ):
        print(
            "Deleting user: "
            + user.username
            + " - "
            + user.email
            + " - "
            + str(user.last_login.date())
        )
        user.delete()

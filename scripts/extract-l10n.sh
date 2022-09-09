#! /bin/bash
#
# This script will do the following:
#   - checkout and update git master branch
#   - create a new branch (name should look like l10n-extract-<date>-<rev>)
#   - Extract new strings and update the .po/.pot files
#   - Commit that extraction to the branch
#
# If you provide a GITHUB_TOKEN variable to the environment then this script
# can also automatically push to a remote branch and create a pull request for
# you through addons-robot. Ask @diox or @muffinresearch for this token.

# Exit immediately when a command fails.
set -e

# Make sure exit code are respected in a pipeline.
set -o pipefail

# Treat unset variables as an error an exit immediately.
set -u

# Extraction needs our django settings for jinja, so we need a django settings
# module set. Since this command is meant to be run in local envs, we use
# "settings".
DJANGO_SETTINGS_MODULE=settings

INITIAL_GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
GIT_CHANGES=$(git status --porcelain)
GIT_REMOTE="https://github.com/mozilla/kitsune.git"  # Upstream.
REV=""
MESSAGE=""
BRANCH_NAME=""
ROBOT_EMAIL=""
ROBOT_NAME="Mozilla Add-ons Robot"

# gettext flags
CLEAN_FLAGS="--no-obsolete --width=200 --no-location"
MERGE_FLAGS="--update --width=200 --backup=none"
UNIQ_FLAGS="--width=200"

info() {
  local message="$1"

  echo ""
  echo "INFO: $message"
  echo ""
}

error() {
  local message="$1"

  echo "ERROR: $message"
  exit 1
}

function init_environment {
    # Detect local (uncommitted) changes.
    if [[ ! -z "$GIT_CHANGES" ]]; then
      error "You have local changes, therefore this script cannot continue."
    fi

    # Switch to the `main` branch if we are not on it already.
    if [[ "$INITIAL_GIT_BRANCH" != "main" ]]; then
      git checkout main
    fi

    # Make sure the 'master' branch is up-to-date.
    git pull "$GIT_REMOTE" main

    REV=$(git rev-parse --short HEAD)
    MESSAGE="Extracted l10n messages from $(date -u +"%Y-%m-%dT%H-%M-%S") at $REV"
    BRANCH_NAME="l10n-extract-$(date -u +"%Y-%m-%dT%H-%M-%S")-$REV"

    # Ensure the branch to extract the locales is clean.
    if [[ $(git branch --list "$BRANCH_NAME") ]]; then
      info "Deleting branch '$BRANCH_NAME' because it already exists"
      git branch -D "$BRANCH_NAME"
    fi

    info "Creating and switching to branch '$BRANCH_NAME'"
    git checkout -b "$BRANCH_NAME"

    make init
    make build
}

function run_l10n_extraction {
    PYTHONPATH=. DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE} pybabel extract -F babel.cfg -o locale/templates/LC_MESSAGES/django.pot -c 'L10n:' -w 80 --version=1.0 --project=kitsune --copyright-holder=Mozilla .
    PYTHONPATH=. DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE} pybabel extract -F babeljs.cfg -o locale/templates/LC_MESSAGES/djangojs.pot -c 'L10n:' -w 80 --version=1.0 --project=kitsune --copyright-holder=Mozilla .

    pushd locale > /dev/null

    info "Merging any new keys..."
    for i in `find . -name "django.po" | grep -v "en_US"`; do
        msguniq $UNIQ_FLAGS -o "$i" "$i"
        msgmerge $MERGE_FLAGS "$i" "templates/LC_MESSAGES/django.pot"
    done
    msgen templates/LC_MESSAGES/django.pot | msgmerge $MERGE_FLAGS en_US/LC_MESSAGES/django.po -

    info "Merging any new javascript keys..."
    for i in `find . -name "djangojs.po" | grep -v "en_US"`; do
        msguniq $UNIQ_FLAGS -o "$i" "$i"
        msgmerge $MERGE_FLAGS "$i" "templates/LC_MESSAGES/djangojs.pot"
    done
    msgen templates/LC_MESSAGES/djangojs.pot | msgmerge $MERGE_FLAGS en_US/LC_MESSAGES/djangojs.po -

    info "Cleaning out obsolete messages..."
    for i in `find . -name "django.po"`; do
        msgattrib $CLEAN_FLAGS --output-file=$i $i
    done
    for i in `find . -name "djangojs.po"`; do
        msgattrib $CLEAN_FLAGS --output-file=$i $i
    done

    msgfilter -i sr/LC_MESSAGES/django.po -o sr_Latn/LC_MESSAGES/django.po recode-sr-latin

    popd > /dev/null

    info "Done extracting."
}

function commit {
    info "Committing...lets not commit actually, we are making sure stuff works first"
    #git -c user.name="$ROBOT_NAME" -c user.email="$ROBOT_EMAIL" commit -m "$MESSAGE" --author "$ROBOT_NAME <$ROBOT_EMAIL>" --no-gpg-sign locale/*/LC_MESSAGES/*.po locale/templates/
    #info "Committed locales extraction to local branch."
}


function generate_post_data()
{
  cat <<EOF
{
    "title": "$MESSAGE",
    "head": "$BRANCH_NAME",
    "base":"master"
}
EOF
}


function create_pull_request {
    info "Pushing the branch...not really pushing, just testing right now..."
    #git push -q "https://addons-robot:$GITHUB_TOKEN@github.com/mozilla/addons-server/"
    info "Creating the auto merge pull request for $BRANCH_NAME ...not really, just testing right now..."
    #curl --verbose -H "Authorization: token $GITHUB_TOKEN" --data "$(generate_post_data)" "https://api.github.com/repos/mozilla/addons-server/pulls"
    info "Pull request NOT really created."
}


init_environment

run_l10n_extraction

commit


# This script is meant to be run inside a virtualenv or inside our docker
# container. If it's the latter, it doesn't necessarily have access to the ssh
# config, therefore we can't reliably push and create a pull request without a
# GitHub API token.
if [[ -z "${GITHUB_TOKEN-}" ]]
then
    info "No github token present. You should now go back to your normal environment to push this branch and create the pull request."
else
    create_pull_request
fi

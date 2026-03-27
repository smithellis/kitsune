#!/bin/bash

# set test environment variables
source bin/test-env.sh

set -ex

# wait on database in DATABASE_URL to be ready
urlwait

./manage.py test --noinput --force-color --timing --parallel=auto --exclude-tag no_parallel $@
./manage.py test --noinput --force-color --timing --tag no_parallel $@

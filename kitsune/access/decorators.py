from functools import wraps
from urllib.parse import quote

from django.contrib.auth import REDIRECT_FIELD_NAME
from django.http import Http404, HttpResponseForbidden, HttpResponseRedirect

from kitsune.sumo.urlresolvers import reverse


def user_access_decorator(
    redirect_func, redirect_url_func, deny_func=None, redirect_field=REDIRECT_FIELD_NAME
):
    """
    Helper function that returns a decorator.

    * redirect func ----- If truthy, a redirect will occur
    * deny_func --------- If truthy, HttpResponseForbidden is returned.
    * redirect_url_func - Evaluated at view time, returns the redirect URL
                          i.e. where to go if redirect_func is truthy.
    * redirect_field ---- What field to set in the url, defaults to Django's.
                          Set this to None to exclude it from the URL.

    """

    def decorator(view_fn):
        def _wrapped_view(request, *args, **kwargs):
            redirect = redirect_func(request.user)
            if redirect and not request.headers.get("x-requested-with") == "XMLHttpRequest":
                # We must call reverse at the view level, else the threadlocal
                # locale prefixing doesn't take effect.
                redirect_url = redirect_url_func() or reverse("users.login")

                # Redirect back here afterwards?
                if redirect_field:
                    path = quote(request.get_full_path())
                    redirect_url = "{}?{}={}".format(redirect_url, redirect_field, path)

                return HttpResponseRedirect(redirect_url)
            elif (redirect and (request.headers.get("x-requested-with") == "XMLHttpRequest")) or (
                deny_func and deny_func(request.user)
            ):
                return HttpResponseForbidden()

            return view_fn(request, *args, **kwargs)

        return wraps(view_fn)(_wrapped_view)

    return decorator


def logout_required(redirect):
    """Requires that the user *not* be logged in."""

    def redirect_func(user):
        return user.is_authenticated

    if callable(redirect):
        return user_access_decorator(
            redirect_func, redirect_field=None, redirect_url_func=lambda: reverse("home")
        )(redirect)
    else:
        return user_access_decorator(
            redirect_func, redirect_field=None, redirect_url_func=lambda: redirect
        )


def login_required(func, login_url=None, redirect=REDIRECT_FIELD_NAME, only_active=True):
    """Requires that the user is logged in."""
    if only_active:

        def redirect_func(user):
            return not (user.is_authenticated and user.is_active)

    else:

        def redirect_func(user):
            return not user.is_authenticated

    return user_access_decorator(
        redirect_func, redirect_field=redirect, redirect_url_func=lambda: login_url
    )(func)


def permission_required(perm, login_url=None, redirect=REDIRECT_FIELD_NAME, only_active=True):
    """A replacement for django.contrib.auth.decorators.permission_required
    that doesn't ask authenticated users to log in."""
    if only_active:

        def deny_func(user):
            return not (user.is_active and user.has_perm(perm))

    else:

        def deny_func(user):
            return not user.has_perm(perm)

    return user_access_decorator(
        lambda u: not u.is_authenticated,
        redirect_field=redirect,
        redirect_url_func=lambda: login_url,
        deny_func=deny_func,
    )


def group_required(group_name, only_active=True):
    """Requires that the user is in the given group. Raises 404 if not."""

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                raise Http404

            if only_active:
                if not (
                    request.user.is_active and request.user.groups.filter(name=group_name).exists()
                ):
                    raise Http404
            elif not request.user.groups.filter(name=group_name).exists():
                raise Http404

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator

import json
from functools import wraps

from django import http
from django.conf import settings
from django.core.exceptions import PermissionDenied

from kitsune.sumo.utils import is_ratelimited

# Copy/pasta from from https://gist.github.com/1405096
# TODO: Log the hell out of the exceptions.
JSON = "application/json"


def json_view(f):
    """Ensure the response content is well-formed JSON.

    Views wrapped in @json_view can return JSON-serializable Python objects,
    like lists and dicts, and the decorator will serialize the output and set
    the correct Content-type.

    Views may also throw known exceptions, like Http404, PermissionDenied,
    etc, and @json_view will convert the response to a standard JSON error
    format, and set the status code and content type.

    """

    @wraps(f)
    def _wrapped(req, *a, **kw):
        try:
            ret = f(req, *a, **kw)
            blob = json.dumps(ret)
            return http.HttpResponse(blob, content_type=JSON)
        except http.Http404 as e:
            blob = json.dumps(
                {
                    "success": False,
                    "error": 404,
                    "message": str(e),
                }
            )
            return http.HttpResponseNotFound(blob, content_type=JSON)
        except PermissionDenied as e:
            blob = json.dumps(
                {
                    "success": False,
                    "error": 403,
                    "message": str(e),
                }
            )
            return http.HttpResponseForbidden(blob, content_type=JSON)
        except Exception as e:
            blob = json.dumps(
                {
                    "success": False,
                    "error": 500,
                    "message": str(e),
                }
            )
            return http.HttpResponseServerError(blob, content_type=JSON)

    return _wrapped


def cors_enabled(origin, methods=None):
    """A simple decorator to enable CORS."""

    if methods is None:
        methods = ["GET"]
    def decorator(f):
        @wraps(f)
        def decorated_func(request, *args, **kwargs):
            if request.method == "OPTIONS":
                # preflight
                if (
                    "HTTP_ACCESS_CONTROL_REQUEST_METHOD" in request.META
                    and "HTTP_ACCESS_CONTROL_REQUEST_HEADERS" in request.META
                ):
                    response = http.HttpResponse()
                    response["Access-Control-Allow-Methods"] = ", ".join(methods)

                    # TODO: We might need to change this
                    response["Access-Control-Allow-Headers"] = request.META[
                        "HTTP_ACCESS_CONTROL_REQUEST_HEADERS"
                    ]
                else:
                    return http.HttpResponseBadRequest()
            elif request.method in methods:
                response = f(request, *args, **kwargs)
            else:
                return http.HttpResponseBadRequest()

            response["Access-Control-Allow-Origin"] = origin
            return response

        return decorated_func

    return decorator


def ratelimit(name, rate, method="POST"):
    """
    Reimplement ``ratelimit.decorators.ratelimit``, using a sumo-specic ``is_ratelimited``.

    This discards a lot of the flexibility of the original, and in turn is a lot simpler.
    """

    def _decorator(fn):
        @wraps(fn)
        def _wrapped(request, *args, **kwargs):
            # Sets ``request.limited`` on ``request``.
            is_ratelimited(request, name, rate, method)
            return fn(request, *args, **kwargs)

        return _wrapped

    return _decorator


def skip_if_read_only_mode(fn):
    """
    Ensures that the decorated function will be skipped if we're in read-only mode.
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not settings.READ_ONLY:
            return fn(*args, **kwargs)

    return wrapper

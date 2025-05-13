from django.conf import settings
from graphene_django.views import GraphQLView


class KitsuneGraphQLView(GraphQLView):
    """Custom GraphQL view for Kitsune that supports test introspection flag."""

    def dispatch(self, request, *args, **kwargs):
        # If in test mode and the introspection test flag cookie is set,
        # set a flag on the request object
        if settings.TEST and "is_test_introspection" in request.COOKIES:
            request.is_test_introspection = request.COOKIES.get("is_test_introspection") == "false"

        return super().dispatch(request, *args, **kwargs)

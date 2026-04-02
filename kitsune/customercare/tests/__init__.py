import factory

from kitsune.customercare.models import SupportTicket
from kitsune.products.tests import ProductFactory
from kitsune.users.tests import UserFactory


class SupportTicketFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SupportTicket

    subject = factory.Faker("sentence")
    description = factory.Faker("paragraph")
    category = "other"
    email = factory.Faker("email")
    product = factory.SubFactory(ProductFactory)
    user = factory.SubFactory(UserFactory)
    submission_status = SupportTicket.STATUS_SENT

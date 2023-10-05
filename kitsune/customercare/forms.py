from django import forms
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _lazy

from kitsune.customercare.zendesk import OS_CHOICES, ZendeskClient

PRODUCTS_WITH_OS = ["firefox-private-network-vpn"]


class ZendeskForm(forms.Form):
    """Form for submitting a ticket to Zendesk."""

    product = forms.CharField(disabled=True, widget=forms.HiddenInput)
    category = forms.ChoiceField(label=_lazy("What do you need help with?"))
    os = forms.ChoiceField(
        label=_lazy("What operating system does your device use?"),
        choices=OS_CHOICES,
        required=False,
    )
    subject = forms.CharField(label=_lazy("Subject"), required=False)
    description = forms.CharField(label=_lazy("Tell us more"), widget=forms.Textarea())
    country = forms.CharField(widget=forms.HiddenInput)

    def __init__(self, *args, product, user=None, categories=None, **kwargs):
        kwargs.update({"initial": {"product": product.slug}})
        super().__init__(*args, **kwargs)
        self.fields["category"].choices = categories if categories is not None else []
        if product.slug == "mozilla-account" and not user.is_authenticated:
            self.fields["subject"].widget.attrs.update({"value": "Loginless Support MA"})
            self.fields["subject"].widget = forms.HiddenInput()
            self.fields["description"].label = mark_safe(
                "Tell us more:<br>Include details such as your account email or specifics about"
                " your sign-in issue to help us get you back into your account quicker."
            )

        if product.slug not in PRODUCTS_WITH_OS:
            del self.fields["os"]

    def send(self, user):
        client = ZendeskClient()
        return client.create_ticket(user, self.cleaned_data)

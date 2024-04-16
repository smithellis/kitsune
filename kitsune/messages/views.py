import json

from django.contrib import messages as contrib_messages
from django.contrib.auth.models import Group
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_POST

from kitsune.access.decorators import login_required
from kitsune.messages import MESSAGES_PER_PAGE
from kitsune.messages.forms import MessageForm, ReplyForm
from kitsune.messages.models import InboxMessage, OutboxMessage
from kitsune.messages.tasks import send_message
from kitsune.sumo.urlresolvers import reverse
from kitsune.sumo.utils import is_ratelimited, paginate


@login_required
def inbox(request):
    user = request.user
    messages = InboxMessage.objects.filter(to=user).order_by("-created")
    count = messages.count()

    messages = paginate(request, messages, per_page=MESSAGES_PER_PAGE, count=count)

    return render(request, "messages/inbox.html", {"msgs": messages})


@login_required
def read(request, msgid):
    message = get_object_or_404(InboxMessage, pk=msgid, to=request.user)
    was_new = message.unread
    if was_new:
        message.update(read=True)
    initial = {"to": message.sender, "in_reply_to": message.pk}
    form = ReplyForm(initial=initial)
    response = render(request, "messages/read.html", {"message": message, "form": form})
    return response


@login_required
def read_outbox(request, msgid):
    message = get_object_or_404(OutboxMessage, pk=msgid, sender=request.user)
    return render(
        request,
        "messages/read-outbox.html",
        {
            "message": _add_recipients(message),
            "to_users": message.to.all(),
            "to_groups": message.to_group.all(),
        },
    )


@login_required
def outbox(request):
    user = request.user
    messages = OutboxMessage.objects.filter(sender=user).order_by("-created")

    messages = paginate(request, messages, per_page=MESSAGES_PER_PAGE)

    for msg in messages.object_list:
        _add_recipients(msg)

    return render(request, "messages/outbox.html", {"msgs": messages})


@login_required
def new_message(request):
    """Send a new private message."""
    if request.method == "GET":
        form = MessageForm(initial=request.GET.dict(), user=request.user)
    elif request.method == "POST":
        form = MessageForm(request.POST, user=request.user)
        if form.is_valid() and not is_ratelimited(request, "private-message-day", "50/d"):
            if (
                any(isinstance(obj, Group) for obj in form.cleaned_data["to"])
                and not request.user.profile.in_staff_group
            ):
                contrib_messages.add_message(
                    request,
                    contrib_messages.ERROR,
                    _("You can't send messages to groups. Please select only users."),
                )
                return render(request, "messages/new.html", {"form": form})
            send_message.delay(
                form.cleaned_data["to"],
                text=form.cleaned_data["message"],
                sender=request.user,
            )
            if "in_reply_to" in form.cleaned_data and form.cleaned_data["in_reply_to"]:
                InboxMessage.objects.filter(
                    pk=form.cleaned_data["in_reply_to"], to=request.user
                ).update(replied=True)

            contrib_messages.add_message(
                request, contrib_messages.SUCCESS, _("Your message was sent!")
            )
            return HttpResponseRedirect(reverse("messages.outbox"))

    return render(request, "messages/new.html", {"form": form})


@login_required
def bulk_action(request, msgtype="inbox"):
    """Apply action to selected messages."""
    msgids = request.POST.getlist("id")

    if len(msgids) == 0:
        contrib_messages.add_message(
            request, contrib_messages.ERROR, _("No messages selected. Please try again.")
        )
    else:
        if "delete" in request.POST:
            return delete(request, msgtype=msgtype)
        elif "mark_read" in request.POST and msgtype == "inbox":
            messages = InboxMessage.objects.filter(pk__in=msgids, to=request.user)
            messages.update(read=True)
        elif "mark_unread" in request.POST and msgtype == "inbox":
            messages = InboxMessage.objects.filter(pk__in=msgids, to=request.user)
            messages.update(read=False)

    return redirect("messages.%s" % msgtype)


@login_required
def delete(request, msgid=None, msgtype="inbox"):
    if msgid:
        msgids = [msgid]
    else:
        try:
            msgids = [int(m) for m in request.POST.getlist("id")]
        except ValueError:
            return HttpResponseBadRequest()

    if msgtype == "inbox":
        messages = InboxMessage.objects.filter(pk__in=msgids, to=request.user)
    else:
        messages = OutboxMessage.objects.filter(pk__in=msgids, sender=request.user)

    if request.method == "POST" and "confirmed" in request.POST:
        if messages.count() != len(msgids):
            contrib_messages.add_message(
                request, contrib_messages.ERROR, _("Messages didn't add up. Try again.")
            )
        else:
            messages.delete()
            msg = ngettext("The message was deleted!", "The messages were deleted!", len(msgids))
            contrib_messages.add_message(request, contrib_messages.SUCCESS, msg)

        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return HttpResponse(json.dumps({"message": m} for m in messages))

        return HttpResponseRedirect(reverse("messages.{t}".format(t=msgtype)))

    if msgtype == "outbox":
        for message in messages:
            _add_recipients(message)

    return render(
        request, "messages/delete.html", {"msgs": messages, "msgid": msgid, "msgtype": msgtype}
    )


@require_POST
@login_required
def preview_async(request):
    """Ajax preview of posts."""
    m = OutboxMessage(sender=request.user, message=request.POST.get("content", ""))
    return render(request, "messages/includes/message_preview.html", {"message": m})


def _add_recipients(msg):
    # Fetch all recipients and groups at once
    recipients = list(msg.to.all())
    groups = list(msg.to_group.all())

    # Set the counts based on the lists
    msg.recipients = len(recipients)
    msg.to_groups_count = len(groups)

    # Assign the recipient based on the number of recipients
    if msg.recipients == 1:
        msg.recipient = recipients[0]
    else:
        msg.recipient = None

    # Assign the group(s) based on the number of groups
    if msg.to_groups_count == 1:
        msg.to_groups = groups[0]
    else:
        msg.to_groups = groups

    return msg

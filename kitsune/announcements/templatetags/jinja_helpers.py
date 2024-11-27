from django_jinja import library

from kitsune.announcements.models import Announcement


@library.global_function
def get_announcements(request):
    user = request.user if request.user.is_authenticated else None
    if user:
        return Announcement.get_for_groups(user.groups.values_list("id", flat=True))
    return Announcement.get_site_wide()


@library.global_function
def get_slides(request):
    # Delete this after development completes
    slides = [
        {
            "icon": "/static/sumo/img/mozilla-support.svg",
            "icon_alt": "Mozilla Support Icon",
            "title": "Firefox 126 Release",
            "description": "Firefox version 126 is live! Learn about what’s changed"
            " and how you can help support the new release.",
            "link": {
                "url": "https://www.mozilla.org/firefox/126-release-notes/",
                "text": "Read the release notes",
            },
        },
        {
            "icon": "/static/icons/survey.svg",
            "icon_alt": "Survey Icon",
            "title": "2024 Contributor Survey",
            "description": "We want to hear from you! Take the survey and help us"
            " improve Firefox and our community.",
            "link": {
                "url": "https://www.mozilla.org/contributor-survey-2024/",
                "text": "Take the survey",
            },
        },
        {
            "icon": "/static/icons/sunset.svg",
            "icon_alt": "Sunset Icon",
            "title": "Mozilla Hubs Sunset",
            "description": "Mozilla Hubs is evolving. Learn about the changes"
            "and the future of immersive web experiences.",
            "link": {"url": "https://www.mozilla.org/hubs-sunset/", "text": "Learn more"},
        },
    ]
    return slides

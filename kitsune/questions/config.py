from collections import OrderedDict

from django.utils.translation import gettext_lazy as _lazy

# The number of answers per page.
ANSWERS_PER_PAGE = 20

# The number of questions per page.
QUESTIONS_PER_PAGE = 20

# Highest ranking to show for a user
HIGHEST_RANKING = 100

# Special tag names:
NEEDS_INFO_TAG_NAME = "needsinfo"
OFFTOPIC_TAG_NAME = "offtopic"

# How long until a question is automatically taken away from a user
TAKE_TIMEOUT = 600

# AAQ config:
products = OrderedDict(
    [
        (
            "desktop",
            {
                "name": _lazy("Firefox"),
                "subtitle": _lazy("Web browser for Windows, Mac and Linux"),
                "extra_fields": ["troubleshooting", "ff_version", "os"],
                "tags": ["desktop"],
                "product": "firefox",
                "categories": OrderedDict(
                    [
                        # TODO: Just use the IA topics for this.
                        # See bug 979397
                        (
                            "install-and-update",
                            {
                                "name": _lazy("Install and update"),
                                "topic": "install-and-update",
                                "tags": ["install-and-update"],
                            },
                        ),
                        (
                            "protect-your-privacy",
                            {
                                "name": _lazy("Protect your privacy"),
                                "topic": "protect-your-privacy",
                                "tags": ["protect-your-privacy"],
                            },
                        ),
                        (
                            "customize",
                            {
                                "name": _lazy("Customize settings and preferences"),
                                "topic": "customize-settings-and-preferences",
                                "tags": ["customize-settings-and-preferences"],
                            },
                        ),
                        (
                            "troubleshooting",
                            {
                                "name": _lazy("Troubleshooting"),
                                "topic": "troubleshooting",
                                "tags": ["troubleshooting"],
                            },
                        ),
                        (
                            "tips",
                            {
                                "name": _lazy("Tips and tricks"),
                                "topic": "tips",
                                "tags": ["tips"],
                            },
                        ),
                        (
                            "bookmarks",
                            {
                                "name": _lazy("Bookmarks"),
                                "topic": "bookmarks",
                                "tags": ["bookmarks"],
                            },
                        ),
                        (
                            "cookies",
                            {
                                "name": _lazy("Cookies"),
                                "topic": "cookies",
                                "tags": ["cookies"],
                            },
                        ),
                        (
                            "tabs",
                            {
                                "name": _lazy("Tabs"),
                                "topic": "tabs",
                                "tags": ["tabs"],
                            },
                        ),
                        (
                            "website-breakages",
                            {
                                "name": _lazy("Website breakages"),
                                "topic": "website-breakages",
                                "tags": ["website-breakages"],
                            },
                        ),
                        (
                            "sync",
                            {
                                "name": _lazy("Firefox Sync"),
                                "topic": "sync",
                                "tags": ["sync"],
                            },
                        ),
                        (
                            "other",
                            {
                                "name": _lazy("Other"),
                                "topic": "other",
                                "tags": ["other"],
                            },
                        ),
                    ]
                ),
            },
        ),
        (
            "mobile",
            {
                "name": _lazy("Firefox for Android"),
                "subtitle": _lazy("Web browser for Android smartphones and tablets"),
                "extra_fields": ["ff_version", "os"],
                "tags": ["mobile"],
                "product": "mobile",
                "categories": OrderedDict(
                    [
                        # TODO: Just use the IA topics for this.
                        # See bug 979397
                        (
                            "install-and-update",
                            {
                                "name": _lazy("Install and update"),
                                "topic": "install-and-update",
                                "tags": ["install-and-update"],
                            },
                        ),
                        (
                            "protect-your-privacy",
                            {
                                "name": _lazy("Protect your privacy"),
                                "topic": "protect-your-privacy",
                                "tags": ["protect-your-privacy"],
                            },
                        ),
                        (
                            "customize",
                            {
                                "name": _lazy("Customize settings and preferences"),
                                "topic": "customize-settings-and-preferences",
                                "tags": ["customize-settings-and-preferences"],
                            },
                        ),
                        (
                            "troubleshooting",
                            {
                                "name": _lazy("Troubleshooting"),
                                "topic": "troubleshooting",
                                "tags": ["troubleshooting"],
                            },
                        ),
                        (
                            "tips",
                            {
                                "name": _lazy("Tips and tricks"),
                                "topic": "tips",
                                "tags": ["tips"],
                            },
                        ),
                        (
                            "bookmarks",
                            {
                                "name": _lazy("Bookmarks"),
                                "topic": "bookmarks",
                                "tags": ["bookmarks"],
                            },
                        ),
                        (
                            "cookies",
                            {
                                "name": _lazy("Cookies"),
                                "topic": "cookies",
                                "tags": ["cookies"],
                            },
                        ),
                        (
                            "tabs",
                            {
                                "name": _lazy("Tabs"),
                                "topic": "tabs",
                                "tags": ["tabs"],
                            },
                        ),
                        (
                            "websites",
                            {
                                "name": _lazy("Websites"),
                                "topic": "websites",
                                "tags": ["websites"],
                            },
                        ),
                        (
                            "sync",
                            {
                                "name": _lazy("Firefox Sync"),
                                "topic": "sync",
                                "tags": ["sync"],
                            },
                        ),
                        (
                            "other",
                            {
                                "name": _lazy("Other"),
                                "topic": "other",
                                "tags": ["other"],
                            },
                        ),
                    ]
                ),
            },
        ),
        (
            "ios",
            {
                "name": _lazy("Firefox for iOS"),
                "subtitle": _lazy("Firefox for iPhone, iPad and iPod touch devices"),
                "extra_fields": ["ff_version", "os"],
                "tags": ["ios"],
                "product": "ios",
                "categories": OrderedDict(
                    [
                        (
                            "install-and-update",
                            {
                                "name": _lazy("Install and update"),
                                "topic": "install-and-update",
                                "tags": ["install-and-update"],
                            },
                        ),
                        (
                            "how-to-use-firefox-ios",
                            {
                                "name": _lazy("How to use Firefox for iOS"),
                                "topic": "how-to-use-firefox-ios",
                                "tags": ["how-to-use-firefox-ios"],
                            },
                        ),
                        (
                            "troubleshooting",
                            {
                                "name": _lazy("Troubleshooting"),
                                "topic": "troubleshooting",
                                "tags": ["troubleshooting"],
                            },
                        ),
                        (
                            "sync",
                            {
                                "name": _lazy("Sync"),
                                "topic": "save-and-share-firefox-ios",
                                "tags": ["sync"],
                            },
                        ),
                        (
                            "bookmarks",
                            {
                                "name": _lazy("Bookmarks"),
                                "topic": "bookmarks-and-tabs-firefox-ios",
                                "tags": ["bookmarks"],
                            },
                        ),
                        (
                            "tabs",
                            {
                                "name": _lazy("Tabs"),
                                "topic": "bookmarks-and-tabs-firefox-ios",
                                "tags": ["tabs"],
                            },
                        ),
                        (
                            "protect-your-privacy",
                            {
                                "name": _lazy("Protect your privacy"),
                                "topic": "protect-your-privacy",
                                "tags": ["protect-your-privacy"],
                            },
                        ),
                    ]
                ),
            },
        ),
        (
            "firefox-enterprise",
            {
                "name": _lazy("Firefox for Enterprise"),
                "subtitle": _lazy("Firefox Quantum for businesses"),
                "extra_fields": ["ff_version", "os"],
                "tags": [],
                "product": "firefox-enterprise",
                "categories": OrderedDict(
                    [
                        (
                            "install-and-update",
                            {
                                "name": _lazy("Install and update"),
                                "topic": "install-and-update",
                                "tags": ["deployment", "install-and-update"],
                            },
                        ),
                        (
                            "install-and-manage-add-ons",
                            {
                                "name": _lazy("Install and manage add-ons"),
                                "topic": "install-and-manage-add-ons",
                                "tags": ["customization", "install-and-manage-add-ons"],
                            },
                        ),
                        (
                            "customize",
                            {
                                "name": _lazy("Customize settings and preferences"),
                                "topic": "customize-settings-and-preferences",
                                "tags": ["customize-settings-and-preferences"],
                            },
                        ),
                    ]
                ),
            },
        ),
        (
            "mdn-plus",
            {
                "name": _lazy("MDN Plus"),
                "subtitle": _lazy("MDN Plus provides a custom experience for MDN supporters."),
                "extra_fields": [],
                "tags": ["mdn-plus"],
                "product": "mdn-plus",
                "categories": OrderedDict([]),
            },
        ),
        (
            "firefox-private-network-vpn",
            {
                "name": _lazy("Mozilla VPN"),
                "subtitle": _lazy("VPN for Windows 10, Android and iOS devices"),
                "extra_fields": [],
                "tags": [],
                "product": "firefox-private-network-vpn",
                "categories": OrderedDict(
                    [
                        (
                            "technical",
                            {
                                "name": _lazy("Technical"),
                                "topic": "technical",
                                "tags": ["technical"],
                            },
                        ),
                        (
                            "accounts",
                            {
                                "name": _lazy("Accounts"),
                                "topic": "accounts",
                                "tags": ["accounts"],
                            },
                        ),
                        (
                            "Payments",
                            {
                                "name": _lazy("Payments"),
                                "topic": "payments",
                                "tags": ["payments"],
                            },
                        ),
                        (
                            "Troubleshooting",
                            {
                                "name": _lazy("Troubleshooting"),
                                "topic": "troubleshooting",
                                "tags": ["troubleshooting"],
                            },
                        ),
                    ]
                ),
            },
        ),
        (
            "relay",
            {
                "name": _lazy("Firefox Relay"),
                "subtitle": _lazy("Service that lets you create aliases to hide your real email"),
                "extra_fields": [],
                "tags": ["relay"],
                "product": "relay",
                "categories": OrderedDict([]),
            },
        ),
        (
            "monitor",
            {
                "name": _lazy("Mozilla Monitor"),
                "subtitle": _lazy("Stay informed and take back control of your exposed data"),
                "extra_fields": [],
                "tags": ["monitor"],
                "product": "monitor",
                "categories": OrderedDict([]),
            },
        ),
        (
            "pocket",
            {
                "name": _lazy("Pocket"),
                "subtitle": _lazy("The web’s most intriguing articles"),
                "extra_fields": [],
                "tags": ["pocket"],
                "product": "pocket",
                "categories": OrderedDict([]),
            },
        ),
        (
            "thunderbird",
            {
                "name": _lazy("Thunderbird"),
                "subtitle": _lazy("Email software for Windows, Mac and Linux"),
                "extra_fields": [],
                "tags": [],
                "product": "thunderbird",
                "categories": OrderedDict(
                    [
                        # TODO: Just use the IA topics for this.
                        # See bug 979397
                        (
                            "install-and-update",
                            {
                                "name": _lazy("Install and update"),
                                "topic": "install-and-update",
                                "tags": ["install-and-update"],
                            },
                        ),
                        (
                            "protect-your-privacy",
                            {
                                "name": _lazy("Protect your privacy"),
                                "topic": "protect-your-privacy",
                                "tags": ["protect-your-privacy"],
                            },
                        ),
                        (
                            "customize",
                            {
                                "name": _lazy("Customize settings and preferences"),
                                "topic": "customize-settings-and-preferences",
                                "tags": ["customize-settings-and-preferences"],
                            },
                        ),
                        (
                            "troubleshooting",
                            {
                                "name": _lazy("Troubleshooting"),
                                "topic": "troubleshooting",
                                "tags": ["troubleshooting"],
                            },
                        ),
                        (
                            "calendar",
                            {
                                "name": _lazy("Calendar"),
                                "topic": "calendar",
                                "tags": ["calendar"],
                            },
                        ),
                        (
                            "other",
                            {
                                "name": _lazy("Other"),
                                "topic": "other",
                                "tags": ["other"],
                            },
                        ),
                    ]
                ),
            },
        ),
        (
            "focus",
            {
                "name": _lazy("Firefox Focus"),
                "subtitle": _lazy("Automatic privacy browser and content blocker"),
                "extra_fields": ["ff_version", "os"],
                "tags": ["focus-firefox"],
                "product": "focus-firefox",
                "categories": OrderedDict(
                    [
                        (
                            "Focus-ios",
                            {
                                "name": _lazy("Firefox Focus for iOS"),
                                "topic": "Focus-ios",
                                "tags": ["Focus-ios"],
                            },
                        ),
                        (
                            "firefox-focus-android",
                            {
                                "name": _lazy("Firefox Focus for Android"),
                                "topic": "firefox-focus-android",
                                "tags": ["firefox-focus-android"],
                            },
                        ),
                    ]
                ),
            },
        ),
        (
            "mozilla-account",
            {
                "name": _lazy("Mozilla Account"),
                "subtitle": _lazy("Mozilla account is the account system for Mozilla"),
                "extra_fields": [],
                "tags": [],
                "product": "mozilla-account",
                "categories": OrderedDict([]),
            },
        ),
    ]
)


def add_backtrack_keys(products):
    """Insert 'key' keys so we can go from product or category back to key."""
    for p_k, p_v in products.items():
        p_v["key"] = p_k
        for c_k, c_v in p_v["categories"].items():
            c_v["key"] = c_k


add_backtrack_keys(products)

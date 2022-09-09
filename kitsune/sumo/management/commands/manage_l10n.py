from django.core.management.base import BaseCommand
from babel.messages.frontend import CommandLineInterface


class Command(BaseCommand):
    """
    Allows you to extract strings for localization as well as compile them.
    Extract creates two .pot files - django.pot and djangojs.pot - that contain
    messages to merge into the existing l10n files.
    Update will merge the .pot files into the existing l10n files, which exist
    in locale (if you have the repo downloaded).

    Args:
        -e: Extract strings
        -u: Update strings

    """

    help = "Extracts localizable strings from the codebase. -e to extract, -u to update."

    def add_arguments(self, parser):
        parser.add_argument(
            "-e",
            "--extract",
            help="Extract strings based on babel.cfg and babeljs.cfg",
            action="store_true",
        )

        parser.add_argument(
            "-u",
            "--update",
            help="Update our l10n data",
            action="store_true",
        )

    def handle(self, *args, **options):
        if options["extract"]:
            CommandLineInterface().run(
                [
                    "pybabel",
                    "extract",
                    "-F",
                    "babel.cfg",
                    "-o",
                    "locale/templates/LC_MESSAGES/django.pot",
                    "-k",
                    "_lazy",
                    "-k",
                    "pgettext_lazy",
                    "-c",
                    "L10n",
                    "-w",
                    "80",
                    "--version",
                    "1.0",
                    "--project=kitsune",
                    "--copyright-holder=Mozilla",
                    ".",
                ]
            )
            CommandLineInterface().run(
                [
                    "pybabel",
                    "extract",
                    "-F",
                    "babeljs.cfg",
                    "-o",
                    "locale/templates/LC_MESSAGES/djangojs.pot",
                    "-k",
                    "_lazy",
                    "-k",
                    "pgettext_lazy",
                    "-c",
                    "L10n",
                    "-w",
                    "80",
                    "--version",
                    "1.0",
                    "--project=kitsune",
                    "--copyright-holder=Mozilla",
                    ".",
                ]
            )

            self.stdout.write("Extraction complete.\n")

        if options["update"]:
            CommandLineInterface().run(
                [
                    "pybabel",
                    "update",
                    "-d",
                    "locale/",
                    "-D",
                    "django",
                    "-i",
                    "locale/templates/LC_MESSAGES/django.pot",
                ]
            )
            CommandLineInterface().run(
                [
                    "pybabel",
                    "update",
                    "-d",
                    "locale/",
                    "-D",
                    "djangojs",
                    "-i",
                    "locale/templates/LC_MESSAGES/djangojs.pot",
                ]
            )
            self.stdout.write("Update complete.\n")

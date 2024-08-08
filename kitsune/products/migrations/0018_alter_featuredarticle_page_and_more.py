# Generated by Django 4.2.14 on 2024-08-07 12:30

from django.db import migrations
import django.db.models.deletion
import modelcluster.fields
import wagtail.blocks
import wagtail.fields
import wagtail.snippets.blocks


class Migration(migrations.Migration):

    dependencies = [
        ("wagtailcore", "0093_uploadedfile"),
        ("products", "0017_alter_featuredarticle_page_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="featuredarticle",
            name="page",
            field=modelcluster.fields.ParentalKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="featured_article",
                to="wagtailcore.page",
            ),
        ),
        migrations.AlterField(
            model_name="singleproductindexpage",
            name="body",
            field=wagtail.fields.StreamField(
                [
                    (
                        "search",
                        wagtail.blocks.StructBlock(
                            [
                                (
                                    "title",
                                    wagtail.blocks.CharBlock(max_length=255, required=False),
                                ),
                                (
                                    "placeholder",
                                    wagtail.blocks.CharBlock(max_length=255, required=False),
                                ),
                            ]
                        ),
                    ),
                    (
                        "cta",
                        wagtail.blocks.StructBlock(
                            [
                                ("text", wagtail.blocks.CharBlock(max_length=255, required=True)),
                                ("link", wagtail.blocks.URLBlock(required=True)),
                                (
                                    "type",
                                    wagtail.blocks.ChoiceBlock(
                                        choices=[
                                            ("Community", "Community"),
                                            ("Paid", "Paid"),
                                            ("Other", "Other"),
                                        ]
                                    ),
                                ),
                            ]
                        ),
                    ),
                    (
                        "featured_articles",
                        wagtail.blocks.StructBlock(
                            [
                                (
                                    "featured",
                                    wagtail.blocks.ListBlock(
                                        wagtail.blocks.StructBlock(
                                            [
                                                (
                                                    "document",
                                                    wagtail.snippets.blocks.SnippetChooserBlock(
                                                        required=True, target_model="wiki.Document"
                                                    ),
                                                )
                                            ]
                                        )
                                    ),
                                )
                            ]
                        ),
                    ),
                    (
                        "frequent_topics",
                        wagtail.blocks.StructBlock(
                            [
                                (
                                    "enabled",
                                    wagtail.blocks.BooleanBlock(default=True, required=False),
                                )
                            ]
                        ),
                    ),
                ]
            ),
        ),
    ]

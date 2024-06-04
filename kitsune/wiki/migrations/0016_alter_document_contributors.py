# Generated by Django 4.2.11 on 2024-05-07 16:13

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("wiki", "0015_document_restrict_to_groups"),
    ]

    operations = [
        migrations.AlterField(
            model_name="document",
            name="contributors",
            field=models.ManyToManyField(
                related_name="wiki_contributions", to=settings.AUTH_USER_MODEL
            ),
        ),
    ]
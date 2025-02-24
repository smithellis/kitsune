# Generated by Django 4.2.18 on 2025-02-20 06:04

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0029_remove_profile_avatar"),
    ]

    operations = [
        migrations.AlterField(
            model_name="accountevent",
            name="profile",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="account_events",
                to="users.profile",
            ),
        ),
    ]

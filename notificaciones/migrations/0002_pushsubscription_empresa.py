from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("empresa", "0001_initial"),
        ("notificaciones", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="pushsubscription",
            name="empresa",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="push_subscriptions",
                to="empresa.empresa",
            ),
        ),
    ]

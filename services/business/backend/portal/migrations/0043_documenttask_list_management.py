from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("portal", "0042_baichuan")]

    operations = [
        migrations.AddField(
            model_name="documenttask", name="pinned_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="documenttask", name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

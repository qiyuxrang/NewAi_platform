from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("portal", "0034_agent_hr_guards")]

    operations = [
        migrations.AlterField(
            model_name="gatewaymodel",
            name="timeout_seconds",
            field=models.PositiveIntegerField(default=20,
                validators=[MinValueValidator(1), MaxValueValidator(600)], verbose_name="超时秒数"),
        ),
    ]

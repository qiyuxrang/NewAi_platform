from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("portal", "0043_documenttask_list_management")]

    operations = [
        migrations.RemoveConstraint(model_name="companyqualification", name="baichuan_qual_grade"),
        migrations.AddConstraint(
            model_name="companyqualification",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(category="labor", grade__isnull=True)
                    | models.Q(category="electronic", grade__in=["1", "2"])
                    | models.Q(category="cs", grade__in=["1", "2", "3", "4", "5"])
                    | models.Q(category="cmmi", grade__in=["3", "4", "5"])
                    | models.Q(category="ccrc", grade__in=["1", "2", "3"])
                    | models.Q(category="itss", grade__in=["1", "2", "3", "4"])
                    | models.Q(category="security", grade__in=["1", "2", "3"])
                    | models.Q(category__in=["electronic", "labor", "cs", "cmmi", "ccrc", "itss", "security"], grade__isnull=True)
                ),
                name="baichuan_qual_grade",
            ),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("portal", "0044_baichuan_cs_level_one")]

    operations = [
        migrations.AddField(
            model_name="company",
            name="website_kind",
            field=models.CharField(
                choices=[("corporate", "企业独立官网"), ("group_profile", "集团专属介绍页"), ("official_wechat", "官方公众号")],
                default="corporate", max_length=20,
            ),
        ),
    ]

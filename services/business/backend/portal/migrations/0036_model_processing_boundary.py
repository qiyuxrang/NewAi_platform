from django.db import migrations, models


class Migration(migrations.Migration):
    # Preserve applied migration names; the complete business branch must precede
    # these additions so fresh databases also retain all business tables.
    dependencies = [("portal", "0046_baichuan_assistant_foundation")]

    operations = [
        migrations.AddField(
            model_name="provider",
            name="processing_boundary",
            field=models.CharField(choices=[("internal", "内部处理"), ("external", "外部处理")],
                default="external", help_text="按服务商实际数据处理环境标记；未确认的服务商保守视为外部处理。",
                max_length=16, verbose_name="数据处理边界"),
        ),
        migrations.AddField(
            model_name="modelroute",
            name="allow_external_processing",
            field=models.BooleanField(default=True,
                help_text="关闭后，该业务路由仅可使用明确标记为内部处理的服务商。", verbose_name="允许外部处理"),
        ),
    ]

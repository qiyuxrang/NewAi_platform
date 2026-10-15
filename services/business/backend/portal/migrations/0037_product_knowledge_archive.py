from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("portal", "0036_product_steps")]
    operations = [migrations.AddField(
        model_name="productknowledgeconversation",
        name="archived_at",
        field=models.DateTimeField(blank=True, null=True),
    )]

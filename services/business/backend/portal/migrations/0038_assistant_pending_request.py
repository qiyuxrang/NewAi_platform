from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("portal", "0037_product_knowledge_archive")]
    operations = [migrations.AddField(
        model_name="productknowledgeconversation",
        name="pending_request_id",
        field=models.UUIDField(blank=True, null=True),
    )]

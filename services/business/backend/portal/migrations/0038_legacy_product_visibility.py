"""Keep visibility markers from newer local databases without replacing their data."""
from django.db import migrations, models


class AddFieldIfMissing(migrations.AddField):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        field = model._meta.get_field(self.name)
        with schema_editor.connection.cursor() as cursor:
            columns = schema_editor.connection.introspection.get_table_description(
                cursor, model._meta.db_table)
        if field.column not in {column.name for column in columns}:
            super().database_forwards(app_label, schema_editor, from_state, to_state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        # A rollback must retain markers already owned by the legacy application.
        pass


class Migration(migrations.Migration):
    dependencies = [("portal", "0037_knowledge_access")]

    operations = [
        AddFieldIfMissing("documenttask", "retry_after", models.DateTimeField(null=True, blank=True)),
        AddFieldIfMissing("documenttask", "pinned_at", models.DateTimeField(null=True, blank=True)),
        AddFieldIfMissing("documenttask", "deleted_at", models.DateTimeField(null=True, blank=True)),
        AddFieldIfMissing("productknowledgeconversation", "archived_at", models.DateTimeField(null=True, blank=True)),
        AddFieldIfMissing("productknowledgeconversation", "pending_request_id", models.UUIDField(null=True, blank=True)),
    ]

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class DepartmentWorkflowMigrationTests(TransactionTestCase):
    def test_upgrade_and_rollback_preserve_legacy_engineering_data(self):
        previous = [('portal', '0038_assistant_pending_request')]
        current = [('portal', '0041_preparation_upload_idempotency')]
        executor = MigrationExecutor(connection)
        executor.migrate(previous)
        apps = executor.loader.project_state(previous).apps
        owner = apps.get_model('portal', 'User').objects.create(username='migration-only-owner', password='!')
        job = apps.get_model('portal', 'EngineeringJob').objects.create(owner_id=owner.pk,
            status='completed', region='陕西', result={'legacy': 'unchanged'}, result_sha256='a'*64)
        job_id = job.pk
        try:
            executor = MigrationExecutor(connection); executor.migrate(current)
            apps = executor.loader.project_state(current).apps
            saved = apps.get_model('portal', 'EngineeringJob').objects.get(pk=job_id)
            self.assertEqual(saved.result, {'legacy': 'unchanged'})
            self.assertEqual(saved.result_sha256, 'a'*64)
            self.assertEqual(apps.get_model('portal', 'EngineeringPreparation').objects.count(), 0)
            executor = MigrationExecutor(connection); executor.migrate(previous)
            apps = executor.loader.project_state(previous).apps
            self.assertEqual(apps.get_model('portal', 'EngineeringJob').objects.get(pk=job_id).region, '陕西')
        finally:
            MigrationExecutor(connection).migrate(current)

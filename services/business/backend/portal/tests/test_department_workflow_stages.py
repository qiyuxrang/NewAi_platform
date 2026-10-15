import json
import uuid
import sqlite3
from contextlib import closing
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.test import override_settings

from portal import engineering_preparations as preparations
from portal.engineering_models import EngineeringJob, EngineeringPreparation
from portal.engineering_worker import run_once, claim_job, process_job
from portal.hr_processing_stages import verification_questions
from portal.hr_screening_models import ResumeArtifact, ResumeScreeningBatch, ResumeProcessingStage
from portal.hr_screening_worker import claim_one, process_one
from portal.hr_resume_storage import save_file
from . import test_engineering_api as engineering
from . import test_hr_screening_worker as hr
from .base import PortalTestCase


class EngineeringPreparationTests(PortalTestCase):
    setUp = engineering.EngineeringApiTests.setUp
    root = '/api/engineering/preparations/'

    def create(self):
        result = self.client.post(self.root, {'files': SimpleUploadedFile('清单.xlsx', b'input')}, HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(result.status_code, 201, result.content)
        return result.json()

    def post(self, pk, action, body):
        return self.client.post(f'{self.root}{pk}/{action}/', json.dumps(body), content_type='application/json')

    def ready(self):
        prep = self.create()
        with patch('portal.engineering_worker._invoke', return_value=(0, {'ok': True, 'files': [{'passed': True}]})) as call:
            self.assertTrue(run_once())
            self.assertEqual(call.call_args.args[1], 'inspect')
        return self.client.get(f'{self.root}{prep["id"]}/').json()

    def confirm(self, prep):
        return self.post(prep['id'], 'confirm', {'expected_version': prep['version'], 'basis_sha256': prep['basis_sha256']})

    def test_no_cost_before_confirmation_and_confirmation_is_idempotent(self):
        prep = self.ready()
        self.assertEqual(prep['state'], 'ready')
        self.assertFalse(EngineeringJob.objects.exists())
        self.assertFalse(prep['basis']['online_allowed'])
        first, second = self.confirm(prep), self.confirm(prep)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.json()['job']['id'], second.json()['job']['id'])
        self.assertEqual(EngineeringJob.objects.count(), 1)
        job = EngineeringJob.objects.get()
        self.assertTrue(preparations.guard_confirmed_job(job, preparations.worker.runtime_state()))
        self.assertNotIn('storage_path', json.dumps(first.json()))

    def test_upload_replay_is_idempotent_and_changed_payload_conflicts(self):
        key = str(uuid.uuid4())
        def upload(content):
            return self.client.post(self.root, {'files': SimpleUploadedFile('清单.xlsx', content)}, HTTP_IDEMPOTENCY_KEY=key)
        first, replay, changed = upload(b'input'), upload(b'input'), upload(b'different')
        self.assertEqual((first.status_code, replay.status_code, changed.status_code), (201, 200, 409))
        self.assertEqual(first.json()['id'], replay.json()['id'])
        self.assertEqual(EngineeringPreparation.objects.count(), 1)

    def test_revision_invalidates_confirmation_and_preserves_basis_history(self):
        prep = self.ready()
        result = self.client.post(f'{self.root}{prep["id"]}/revisions/', {
            'expected_version': 1, 'files': SimpleUploadedFile('新清单.xlsx', b'new input'), 'region': '榆林'})
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()['version'], 2)
        self.assertEqual(result.json()['state'], 'queued')
        self.assertEqual(result.json()['basis_sha256'], '')
        self.assertEqual(result.json()['history'][0]['basis_sha256'], prep['basis_sha256'])
        self.assertEqual(self.confirm(prep).status_code, 409)

    def test_rule_drift_or_corrupt_checkpoint_blocks_confirmation(self):
        prep = self.ready()
        self.cli.write_text('# changed pricing', encoding='utf-8')
        self.assertEqual(self.confirm(prep).status_code, 409)
        self.assertFalse(EngineeringJob.objects.exists())
        prep = self.ready()
        EngineeringPreparation.objects.get(pk=prep['id']).steps.update(output={'corrupt': True})
        self.assertEqual(self.confirm(prep).status_code, 409)

    def test_changed_rules_after_confirmation_stop_before_cli(self):
        prep = self.ready()
        self.assertEqual(self.confirm(prep).status_code, 200)
        claim = claim_job()
        self.cli.write_text('# changed pricing', encoding='utf-8')
        with patch('portal.engineering_worker._invoke') as call:
            process_job(*claim)
            call.assert_not_called()
        job = EngineeringJob.objects.get()
        self.assertEqual(job.error_code, 'basis_changed')

    def test_owner_scope_permission_revocation_and_lost_preflight_fence(self):
        prep = self.create()
        self.login(self.client, self.other)
        self.assertEqual(self.client.get(f'{self.root}{prep["id"]}/').status_code, 404)
        self.login(self.client, self.owner)
        def lose(*args, **kwargs):
            EngineeringPreparation.objects.filter(pk=prep['id']).update(fence=99)
            return 0, {'ok': True, 'files': []}
        with patch('portal.engineering_worker._invoke', side_effect=lose):
            preparations.run_once()
        self.assertFalse(EngineeringPreparation.objects.get(pk=prep['id']).steps.exists())
        self.owner.roles.clear()
        self.assertEqual(self.client.get(self.root).status_code, 403)

    def test_empty_legacy_web_cache_creation_is_not_a_price_change(self):
        root = Path(self.temporary.name) / 'prices'
        (root / 'library').mkdir(parents=True)
        with override_settings(ENGINEERING_DATA_ROOT=root):
            config = preparations.worker.runtime_state()
            before = preparations.fingerprint(config)
            with closing(sqlite3.connect(root / 'library/网价缓存.sqlite')) as db:
                db.execute('CREATE TABLE prices (name TEXT, price REAL)')
                self.assertEqual(preparations.fingerprint(config), before)
                db.execute("INSERT INTO prices VALUES ('synthetic', 100)"); db.commit()
            self.assertNotEqual(preparations.fingerprint(config), before)

    def test_corrupt_price_cache_fails_preflight_without_starting_cli(self):
        root = Path(self.temporary.name) / 'bad-prices'
        (root / 'library').mkdir(parents=True)
        (root / 'library/网价缓存.sqlite').write_bytes(b'corrupt database')
        prep = self.create()
        with override_settings(ENGINEERING_DATA_ROOT=root), patch('portal.engineering_worker._invoke') as call:
            preparations.run_once()
            call.assert_not_called()
        current = EngineeringPreparation.objects.get(pk=prep['id'])
        self.assertEqual((current.state, current.error_code), ('failed', 'basis_unavailable'))


class HrProcessingStageTests(PortalTestCase):
    setUp = hr.ScreeningWorkerTests.setUp
    profile_reply = {'content': json.dumps({'skills': {'value': ['SQL'], 'status': 'extracted', 'source_ref': {'quote': '技能：SQL'}}})}
    match_reply = {'content': json.dumps({'requirements': [{'requirement_id': 'skill_requirements#0', 'verdict': 'MATCH', 'evidence': [{'quote': '技能：SQL'}]}]})}

    def requeue(self):
        self.item.refresh_from_db()
        self.item.processing_status, self.item.lease_until = 'queued', None
        self.item.save()
        self.batch.status = 'queued'
        self.batch.save()

    def another(self, *, owner=None, key='second', jd=None):
        owner = owner or self.hr
        batch = ResumeScreeningBatch.objects.create(jd_version=jd or self.batch.jd_version, created_by=owner,
            input_version=1, requirements=self.batch.requirements, idempotency_key=key, status='queued')
        return ResumeArtifact.objects.create(batch=batch, uploaded_by=owner, processing_status='queued',
            **save_file('same.txt', '姓名：合成人\n技能：SQL'.encode()))

    @patch('portal.hr_screening_worker.generate_for_use')
    def test_match_failure_keeps_parse_and_retry_only_runs_match(self, model):
        model.side_effect = [self.profile_reply, ValueError('bad match')]
        process_one(*claim_one())
        self.item.refresh_from_db()
        self.assertEqual(self.item.processing_status, 'failed')
        self.assertEqual(set(self.item.stages.values_list('name', flat=True)), {'extraction', 'profile'})
        self.requeue()
        model.reset_mock(); model.side_effect = [self.match_reply]
        process_one(*claim_one())
        self.item.refresh_from_db()
        self.assertEqual(self.item.processing_status, 'completed', self.item.error_code)
        self.assertEqual([call.args[1] for call in model.call_args_list], ['hr_match_summary'])

    @patch('portal.hr_screening_worker.generate_for_use')
    def test_same_owner_cross_batch_reuses_profile_but_not_match(self, model):
        model.side_effect = [self.profile_reply, self.match_reply]
        process_one(*claim_one())
        second = self.another()
        model.reset_mock(); model.side_effect = [self.match_reply]
        process_one(*claim_one())
        second.refresh_from_db()
        self.assertEqual(second.processing_status, 'completed', second.error_code)
        self.assertEqual([call.args[1] for call in model.call_args_list], ['hr_match_summary'])

    @patch('portal.hr_screening_worker.generate_for_use')
    def test_cross_jd_reuses_only_extraction_and_profile(self, model):
        from portal.hr_recruitment_models import RecruitmentRequest, JDVersion
        model.side_effect = [self.profile_reply, self.match_reply]
        process_one(*claim_one())
        request = RecruitmentRequest.objects.create(created_by=self.hr, updated_by=self.hr, position_name='数据分析师')
        jd = JDVersion.objects.create(request=request, version=1, input_version=1, state='confirmed', body='SQL分析', created_by=self.hr)
        request.current_jd = request.official_jd = jd; request.save()
        second = self.another(jd=jd)
        model.reset_mock(); model.side_effect = [self.match_reply]
        process_one(*claim_one())
        second.refresh_from_db()
        self.assertEqual(second.match['jd_version_id'], str(jd.pk))
        self.assertEqual([call.args[1] for call in model.call_args_list], ['hr_match_summary'])

    @patch('portal.hr_screening_worker.generate_for_use')
    def test_different_owner_never_reuses_private_profile(self, model):
        from portal.hr_recruitment_models import RecruitmentRequest, JDVersion
        model.side_effect = [self.profile_reply, self.match_reply]
        process_one(*claim_one())
        other = self.create_user('other-private-hr', 'hr')
        request = RecruitmentRequest.objects.create(created_by=other, updated_by=other, position_name='工程师')
        jd = JDVersion.objects.create(request=request, version=1, input_version=1, state='confirmed', body='SQL', created_by=other)
        request.current_jd = request.official_jd = jd; request.save()
        second = self.another(owner=other, jd=jd)
        model.reset_mock(); model.side_effect = [self.profile_reply, self.match_reply]
        process_one(*claim_one())
        second.refresh_from_db()
        self.assertEqual(second.processing_status, 'completed', second.error_code)
        self.assertEqual(model.call_count, 2)

    @patch('portal.hr_screening_worker.generate_for_use')
    def test_archived_source_or_corrupt_output_cannot_be_reused(self, model):
        model.side_effect = [self.profile_reply, self.match_reply]
        process_one(*claim_one())
        self.item.stages.filter(name='profile').update(output={'bad': 'checksum'})
        second = self.another()
        model.reset_mock(); model.side_effect = [self.profile_reply, self.match_reply]
        process_one(*claim_one())
        self.assertEqual(model.call_count, 2)
        ResumeArtifact.objects.filter(batch=self.batch).update(archive_state='deleted')
        ResumeArtifact.objects.filter(pk=second.pk).update(archive_state='deleted')
        third = self.another(key='third')
        model.reset_mock(); model.side_effect = [self.profile_reply, self.match_reply]
        process_one(*claim_one())
        third.refresh_from_db()
        self.assertEqual(third.processing_status, 'completed', third.error_code)
        self.assertEqual(model.call_count, 2)

    @patch('portal.hr_screening_worker.generate_for_use')
    def test_expired_lease_cannot_save_model_stage(self, model):
        def expire(*args, **kwargs):
            ResumeArtifact.objects.filter(pk=self.item.pk).update(lease_until=timezone.now()-timedelta(seconds=1))
            return self.profile_reply
        model.side_effect = expire
        process_one(*claim_one())
        self.assertFalse(self.item.stages.filter(name='profile').exists())

    @patch('portal.hr_screening_worker.generate_for_use')
    def test_parse_configuration_change_invalidates_saved_profile(self, model):
        from portal.models import ModelRoute
        hr.ScreeningWorkerTests.select_flash(self)
        model.side_effect = [self.profile_reply, ValueError('match failed')]
        process_one(*claim_one())
        route = ModelRoute.objects.get(code='hr_resume_parse')
        route.name = 'Changed parser configuration'; route.save(update_fields=['name', 'updated_at'])
        self.requeue()
        model.reset_mock(); model.side_effect = [self.profile_reply, self.match_reply]
        process_one(*claim_one())
        self.item.refresh_from_db()
        self.assertEqual(self.item.processing_status, 'completed', self.item.error_code)
        self.assertEqual(model.call_count, 2)

    def test_questions_only_request_evidence_for_unknown_and_partial(self):
        rows = [{'id': verdict, 'text': 'SQL能力', 'verdict': verdict, 'evidence': []}
                for verdict in ['MATCH', 'PARTIAL', 'UNKNOWN', 'NOT_MATCH']]
        self.assertEqual([q['requirement_id'] for q in verification_questions(rows)], ['PARTIAL', 'UNKNOWN'])

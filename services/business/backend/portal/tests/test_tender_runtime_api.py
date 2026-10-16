from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import Client, override_settings
from django.utils import timezone

from portal.tender_api import _official_notice_url
from portal.tender_manual_refresh import enqueue, enqueue_due, serialize
from portal.tender_models import TenderConsumerHeartbeat, TenderFetchRun, TenderManualRefresh, TenderSource
from portal.tender_recovery import confirm_batch, confirm_source
from .base import PortalTestCase


class TenderRuntimeApiTests(PortalTestCase):
    def setUp(self):
        self.user = self.create_user('runtime-board-user', 'product')
        self.client = Client()
        self.login(self.client, self.user)
        self.source = TenderSource.objects.create(code='sx_jk_ecai', name='陕西交控 e 采',
                                                   adapter_code='sx_jk_ecai', enabled=True)

    def test_official_detail_accepts_verified_objtype_only(self):
        notice_id = 'a' * 32
        url = f'https://www.sxjkjcpt.com/portal/detail?docid={notice_id}&chnlcode=tender'
        notice = SimpleNamespace(source=self.source, source_id=self.source.pk,
                                 source_notice_id=notice_id, original_url=url)
        for suffix in ('', '&objtype=2'):
            notice.original_url = url + suffix
            self.assertEqual(_official_notice_url(notice), url + suffix)
        for suffix in ('&objtype=3', '&objtype=', '&objtype=2&objtype=2', '&redirect=', '&redirect=https://evil.test'):
            notice.original_url = url + suffix
            self.assertIsNone(_official_notice_url(notice))

    @override_settings(PORTAL_TENDER_INGESTION_ENABLED=True, PORTAL_TENDER_MANUAL_REFRESH_ENABLED=True)
    def test_latest_completed_schedule_visible_with_real_timestamps_and_safe_details(self):
        now = timezone.now()
        TenderConsumerHeartbeat.objects.create(slot=1, updated_at=now)
        self.source.last_success_at = now
        self.source.save(update_fields=['last_success_at'])
        TenderFetchRun.objects.create(source=self.source, state='SUCCESS', started_at=now,
                                       finished_at=now, stats={'ingested': 3, 'complete': False,
                                                              'notes': 'private technical notes'})
        batch = TenderManualRefresh.objects.create(state='PARTIAL', trigger='scheduled',
            started_at=now, finished_at=now, source_codes=[self.source.code],
            results={self.source.code: {'state': 'SUCCESS', 'ingested': 3, 'complete': False,
                                       'error_detail': 'must not expose'}})
        schedule = {'enabled': True, 'interval_minutes': 60, 'lookback_days': 7,
                    'next_run_at': (now + timedelta(hours=1)).isoformat()}
        with patch('portal.tender_api.schedule_status', return_value=schedule):
            payload = self.client.get('/api/product/refresh/').json()
        self.assertEqual(payload['batch']['id'], str(batch.pk))
        self.assertEqual(payload['batch']['trigger'], 'scheduled')
        self.assertEqual(payload['schedule'], schedule)
        self.assertTrue(payload['consumer_online'])
        self.assertIsNotNone(payload['last_attempt_at'])
        self.assertIsNotNone(payload['last_success_at'])
        result = payload['batch']['results'][self.source.code]
        self.assertNotIn('error_detail', result)
        self.assertIn('尚未全部核验', result['detail'])
        run = self.client.get('/api/product/sources/').json()['items'][0]['latest_run']
        self.assertEqual(run['stats'], {'ingested': 3, 'complete': False})
        self.assertIsNotNone(run['started_at'])
        self.assertIn('尚未全部核验', run['detail'])

    def test_stale_consumer_is_offline_even_when_a_batch_exists(self):
        TenderConsumerHeartbeat.objects.create(slot=1, updated_at=timezone.now() - timedelta(seconds=30))
        TenderManualRefresh.objects.create(requested_by=self.user, state='QUEUED')
        payload = self.client.get('/api/product/refresh/').json()
        self.assertFalse(payload['consumer_online'])
        self.assertFalse(payload['available'])
        self.assertEqual(payload['batch']['state'], 'QUEUED')

    @override_settings(PORTAL_TENDER_INGESTION_ENABLED=True, PORTAL_TENDER_MANUAL_REFRESH_ENABLED=True,
                       PORTAL_TENDER_SCHEDULE_ENABLED=True)
    def test_online_consumer_cannot_hide_interruption_and_explicit_recovery_restores_refresh(self):
        now = timezone.now()
        TenderConsumerHeartbeat.objects.create(slot=1, updated_at=now)
        run = TenderFetchRun.objects.create(source=self.source, state='RUNNING', fence=1,
                                            lease_until=now - timedelta(seconds=1), stats={'ingested': 327})
        batch = TenderManualRefresh.objects.create(state='RUNNING', fence=1, trigger='scheduled',
            source_codes=[self.source.code], lease_until=now - timedelta(seconds=1))
        payload = self.client.get('/api/product/refresh/').json()
        self.assertTrue(payload['consumer_online'])
        self.assertFalse(payload['available'])
        self.assertTrue(payload['recovery_required'])
        self.assertIn('旧执行已停止', payload['unavailable_reason'])
        self.assertEqual(payload['batch']['stored_state'], 'RUNNING')
        self.assertEqual(payload['batch']['display_state'], 'INTERRUPTED')
        self.assertIsNone(payload['schedule']['next_run_at'])
        self.assertIsNone(enqueue_due())
        self.assertEqual(self.client.post('/api/product/refresh/', data={}, content_type='application/json').status_code, 409)
        # Reading status or trying refresh never takes ownership or claims success.
        run.refresh_from_db()
        batch.refresh_from_db()
        self.assertEqual((run.state, run.fence, run.stats), ('RUNNING', 1, {'ingested': 327}))
        self.assertEqual((batch.state, batch.fence), ('RUNNING', 1))
        with override_settings(TENDER_RECOVERY_OPERATOR_IDS=[self.user.pk]):
            confirm_source(run.pk, self.user, '已确认旧采集进程停止')
            confirm_batch(batch.pk, self.user, '已确认旧采集进程停止')
        payload = self.client.get('/api/product/refresh/').json()
        self.assertTrue(payload['available'])
        self.assertFalse(payload['recovery_required'])
        self.assertEqual(payload['unavailable_reason'], '')
        self.assertIsNotNone(payload['schedule']['next_run_at'])
        response = self.client.post('/api/product/refresh/', data={}, content_type='application/json')
        self.assertEqual(response.status_code, 202, response.content)
        self.assertEqual(TenderManualRefresh.objects.filter(state='QUEUED').count(), 1)

    @override_settings(PORTAL_TENDER_INGESTION_ENABLED=True, PORTAL_TENDER_MANUAL_REFRESH_ENABLED=True,
                       PORTAL_TENDER_SCHEDULE_ENABLED=True)
    def test_orphan_source_or_missing_batch_lease_requires_recovery(self):
        now = timezone.now()
        TenderConsumerHeartbeat.objects.create(slot=1, updated_at=now)
        run = TenderFetchRun.objects.create(source=self.source, state='RUNNING',
                                            lease_until=now - timedelta(seconds=1))
        payload = self.client.get('/api/product/refresh/').json()
        self.assertIsNone(payload['batch'])
        self.assertTrue(payload['recovery_required'])
        self.assertFalse(payload['available'])
        self.assertIsNone(payload['schedule']['next_run_at'])
        self.assertIsNone(enqueue_due())
        with self.assertRaisesRegex(ValueError, '上次采集中断'):
            enqueue(self.user, [self.source.code])
        self.assertFalse(TenderManualRefresh.objects.exists())
        run.delete()
        batch = TenderManualRefresh.objects.create(state='RUNNING', lease_until=None)
        self.assertEqual(serialize(batch)['state'], 'INTERRUPTED')
        payload = self.client.get('/api/product/refresh/').json()
        self.assertTrue(payload['recovery_required'])
        self.assertFalse(payload['available'])

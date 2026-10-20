import hashlib
from dataclasses import replace
from datetime import datetime
from tempfile import TemporaryDirectory

from django.test import TestCase, override_settings

from portal.tender_models import TenderNotice, TenderNoticeVersion, TenderOpportunity, TenderSource
from portal.tender_service import backfill_public_fields, backfill_qinyuan_display_fields, ingest_fetch_result
from portal.tender_normalize import normalize_notice
from .test_tender_qinyuan import adapter_and_ref


class TenderDisplayBackfillTests(TestCase):
    def test_procurement_procedure_is_not_a_method_value(self):
        raw = '<p>采用电子招标采购方式，潜在投标人须使用数字CA证书才能完成投标工作。</p>'
        self.assertIsNone(normalize_notice(raw, source_code='qinyuan', original_url='').value_of('procurement_method'))
        self.assertEqual(normalize_notice('<p>采购方式：公开招标</p>', source_code='qinyuan', original_url='').value_of('procurement_method'), '公开招标')

    def setUp(self):
        temporary = TemporaryDirectory(prefix='tender-display-tests-')
        self.addCleanup(temporary.cleanup)
        self.enterContext(override_settings(TENDER_STORAGE_ROOT=temporary.name))
        self.source = TenderSource.objects.create(code='qinyuan', name='秦源', adapter_code='qinyuan')
        adapter, ref, _ = adapter_and_ref()
        self.result = adapter.fetch_detail(ref)

    def test_corrected_project_code_retains_official_notice_identity(self):
        first = ingest_fetch_result(self.result, source=self.source)
        raw = self.result.raw_bytes.replace(b'0866-26E2SXQY0971', b'0866-26E2SXQY0972')
        self.assertNotEqual(raw, self.result.raw_bytes)
        second = ingest_fetch_result(replace(self.result, raw_bytes=raw,
                                            sha256=hashlib.sha256(raw).hexdigest()), source=self.source)
        self.assertEqual(first.opportunity_id, second.opportunity_id)
        self.assertEqual(TenderNotice.objects.count(), 1)
        self.assertEqual(TenderOpportunity.objects.count(), 1)
        self.assertEqual(TenderNoticeVersion.objects.count(), 2)

    def test_display_repair_preserves_version_history_and_timestamps(self):
        outcome = ingest_fetch_result(self.result, source=self.source)
        record = TenderOpportunity.objects.get(pk=outcome.opportunity_id)
        expected = (record.purchaser, record.project_code, record.budget_raw)
        times = (record.first_seen_at, record.updated_at)
        versions = list(TenderNoticeVersion.objects.values())
        TenderOpportunity.objects.filter(pk=record.pk).update(purchaser='为某公司，招标资金来自企业自筹。',
                                                             project_code='bad parse', budget_raw='管理系统采购内容')
        record.refresh_from_db()
        self.assertEqual(backfill_qinyuan_display_fields(record, dry_run=True), 'changed')
        self.assertEqual(TenderOpportunity.objects.get(pk=record.pk).project_code, 'bad parse')
        self.assertEqual(backfill_qinyuan_display_fields(record), 'changed')
        record.refresh_from_db()
        self.assertEqual((record.purchaser, record.project_code, record.budget_raw), expected)
        self.assertEqual((record.first_seen_at, record.updated_at), times)
        self.assertEqual(list(TenderNoticeVersion.objects.values()), versions)
        self.assertEqual(backfill_qinyuan_display_fields(record), 'unchanged')

    def test_stale_display_repair_does_not_replace_newer_record(self):
        record = TenderOpportunity.objects.get(pk=ingest_fetch_result(self.result, source=self.source).opportunity_id)
        TenderOpportunity.objects.filter(pk=record.pk).update(project_code='bad parse')
        record.refresh_from_db()
        TenderOpportunity.objects.filter(pk=record.pk).update(classification_notice_version=None)
        self.assertEqual(backfill_qinyuan_display_fields(record), 'concurrent_change')

    def test_public_backfill_reparses_archived_point_times_without_losing_history_or_real_conflicts(self):
        raw = ('<title>测试采购公告</title><p>发布时间：2026-09-24</p>'
               '<p>投标截止时间：2026年11月11日09点30分</p>'
               '<p>开标时间：2026-11-11 09:30</p>'
               '<p>开标时间：2026年11月11日09点30分</p>').encode()
        result = replace(self.result, raw_bytes=raw, sha256=hashlib.sha256(raw).hexdigest())
        record = TenderOpportunity.objects.get(pk=ingest_fetch_result(result, source=self.source).opportunity_id)
        version = TenderNoticeVersion.objects.get()
        snapshot = version.snapshot
        previous = {'fields': {
            'bid_deadline': {'value': None, 'status': 'UNKNOWN', 'precision': 'date', 'conflict': False,
                             'rule': 'public_document:explicit_date',
                             'raw': '投标截止时间：2026年11月11日09点30分'},
            'bid_open_at': {'value': None, 'status': 'UNKNOWN', 'precision': 'minute', 'conflict': True,
                            'rule': 'public_document:explicit_date',
                            'snippets': ['开标时间：2026-11-11 09:30', '开标时间：2026年11月11日09点30分']},
        }}
        snapshot.source_metadata = {**snapshot.source_metadata, 'public_extraction': previous}
        snapshot.save(update_fields=['source_metadata'])
        TenderOpportunity.objects.filter(pk=record.pk).update(bid_deadline=None, bid_open_at=None,
                                                              status='CLOSED', unknown_fields=['bid_deadline', 'bid_open_at', 'region'])
        record.refresh_from_db()
        times = (record.first_seen_at, record.updated_at)
        versions = list(TenderNoticeVersion.objects.values())
        self.assertEqual(backfill_public_fields(record), 'updated')
        record.refresh_from_db()
        expected = datetime.fromisoformat('2026-11-11T09:30:00+08:00')
        self.assertEqual((record.bid_deadline, record.bid_open_at), (expected, expected))
        self.assertEqual(record.unknown_fields, ['region'])
        self.assertEqual((record.first_seen_at, record.updated_at), times)
        self.assertEqual(record.status, 'CLOSED')
        self.assertEqual(list(TenderNoticeVersion.objects.values()), versions)
        snapshot.refresh_from_db()
        self.assertEqual(snapshot.source_metadata['public_extraction'], previous)
        self.assertEqual(backfill_public_fields(record), 'updated')
        record.refresh_from_db()
        self.assertEqual((record.bid_deadline, record.bid_open_at), (expected, expected))
        # A genuine disagreement in archived evidence still clears the field.
        previous['fields']['bid_open_at']['snippets'][1] = '开标时间：2026年11月11日10点30分'
        snapshot.source_metadata['public_extraction'] = previous
        snapshot.save(update_fields=['source_metadata'])
        self.assertEqual(backfill_public_fields(record), 'updated')
        record.refresh_from_db()
        self.assertIsNone(record.bid_open_at)
        self.assertEqual(record.unknown_fields, ['bid_open_at', 'region'])
        self.assertTrue(record.extraction_evidence['fields']['bid_open_at']['conflict'])
        # The archive caps snippets at six; omitted evidence cannot be ruled out.
        previous['fields']['bid_open_at']['snippets'] = [
            '开标时间：2026-11-11 09:30', '开标时间：2026年11月11日09点30分'] * 3
        snapshot.source_metadata['public_extraction'] = previous
        snapshot.save(update_fields=['source_metadata'])
        self.assertEqual(backfill_public_fields(record), 'updated')
        record.refresh_from_db()
        self.assertIsNone(record.bid_open_at)

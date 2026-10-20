"""Actual SSE iterator lifecycle/authorization tests; no execution on connect."""
import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.sessions.models import Session
from django.test import Client, override_settings
from django.urls import resolve
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from portal.baichuan_assistant_models import BaichuanConversation, BaichuanMessage, BaichuanJob
from portal.baichuan_jobs import enqueue_job
from portal.baichuan_stream import events
from .base import PortalTestCase


class StreamTests(PortalTestCase):
    def setUp(self):
        self.owner = self.create_user('stream-owner', 'product')
        self.other = self.create_user('stream-other', 'product')
        config = override_settings(BAICHUAN_ASSISTANT_ENABLED=True, BAICHUAN_ASSISTANT_SCOPE='stream-test',
            PORTAL_BAICHUAN_SCOPE_CONFIRMED=True, PORTAL_BAICHUAN_READ_USER_IDS=[self.owner.pk, self.other.pk],
            PORTAL_BAICHUAN_WRITE_USER_IDS=[], PORTAL_BAICHUAN_READ_ROLE_CODES=[], PORTAL_BAICHUAN_WRITE_ROLE_CODES=[])
        config.enable(); self.addCleanup(config.disable)
        for target in ('portal.baichuan_assistant_worker.generate_for_use', 'socket.create_connection', 'socket.getaddrinfo'):
            guard = patch(target, side_effect=AssertionError('Observation must never execute work/network'))
            mock = guard.start(); self.addCleanup(guard.stop); self.addCleanup(mock.assert_not_called)
        self.conversation = BaichuanConversation.objects.create(owner=self.owner, scope='stream-test', condition_revision=1)
        self.job = enqueue_job(self.owner, kind='query', conversation=self.conversation,
            payload={'condition_revision': 1}, idempotency_key='stream-job')[0]
        self.path = f'/api/product/baichuan/assistant/jobs/{self.job.pk}/stream/'

    def request(self, user=None, payload=None, path=None):
        path = path or self.path
        req = APIRequestFactory().post(path, {} if payload is None else payload, format='json')
        force_authenticate(req, user=user or self.owner)
        match = resolve(path)
        return match.func(req, **match.kwargs)

    def event(self, iterator):
        raw = next(iterator)
        self.assertTrue(raw.startswith(b'data: ') and raw.endswith(b'\n\n'))
        return json.loads(raw[6:-2])

    def update(self, **changes):
        BaichuanJob.objects.filter(pk=self.job.pk).update(**changes)

    def terminal(self, status='completed', text='已检索：已确认 1 家，待核实 2 家。'):
        BaichuanMessage.objects.create(conversation=self.conversation, role='assistant', content=text,
            condition_revision=1, metadata={'job_id':str(self.job.pk)})
        self.update(status=status)

    def test_first_frame_precedes_work_and_stage_and_fenced_reply_arrive_incrementally(self):
        response = self.request()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/event-stream'))
        self.assertEqual(response['X-Accel-Buffering'], 'no')
        iterator = iter(response.streaming_content)
        self.assertIn('已接收', self.event(iterator)['delta'])
        self.update(status='running', stage='planning')
        self.assertIn('区分硬性', self.event(iterator)['delta'])
        self.update(stage='matching')
        self.assertIn('条件已校验', self.event(iterator)['delta'])
        self.terminal()
        self.assertIn('待核实 2', self.event(iterator)['delta'])
        self.assertEqual(self.event(iterator)['done']['job']['status'], 'completed')
        with self.assertRaises(StopIteration): next(iterator)

    def test_reconnect_and_disconnect_do_not_claim_cancel_or_duplicate_anything(self):
        before = list(BaichuanJob.objects.values()), list(BaichuanMessage.objects.values())
        for _ in range(3):
            stream = events(self.owner, self.job.pk)
            self.assertIn('已接收', self.event(stream)['delta']); stream.close()
        self.assertEqual(before, (list(BaichuanJob.objects.values()), list(BaichuanMessage.objects.values())))

    def test_revocation_between_yields_stops_before_private_reply(self):
        stream = events(self.owner, self.job.pk); self.event(stream)
        self.terminal(text='PRIVATE MUST NOT LEAK')
        self.owner.is_active=False; self.owner.save(update_fields=['is_active'])
        event=self.event(stream)
        self.assertEqual(event['error']['code'], 'scope_revoked')
        self.assertNotIn('PRIVATE', json.dumps(event))
        with self.assertRaises(StopIteration): next(stream)

    def test_session_version_change_is_revoked(self):
        stream=events(self.owner,self.job.pk); self.event(stream)
        type(self.owner).objects.filter(pk=self.owner.pk).update(session_version=self.owner.session_version+1)
        self.assertEqual(self.event(stream)['error']['code'],'scope_revoked')

    def test_new_revision_supersedes_old_stream_without_publishing_old_summary(self):
        stream=events(self.owner,self.job.pk); self.event(stream)
        self.terminal(text='STALE PRIVATE REPLY')
        self.conversation.condition_revision=2; self.conversation.save(update_fields=['condition_revision'])
        event=self.event(stream)
        self.assertTrue(event['done']['superseded'])
        self.assertNotIn('STALE',json.dumps(event))

    def test_cross_owner_missing_scope_and_nonquery_are_denied(self):
        other=self.request(self.other)
        missing=self.request(path=self.path.replace(str(self.job.pk),str(uuid.uuid4())))
        self.assertEqual(other.status_code,404); self.assertEqual(other.data,missing.data)
        self.update(scope='another-deployment')
        self.assertEqual(self.request().status_code,404)
        self.update(scope='stream-test',kind='research')
        self.assertEqual(self.request().status_code,404)

    def test_payload_cannot_start_work_or_set_options(self):
        for payload in ({'text':'execute'}, {'model':'expensive'}, {'budget':None}, []):
            self.assertEqual(self.request(payload=payload).status_code,400)
        self.assertEqual(BaichuanJob.objects.count(),1)

    def test_bounded_window_returns_reconnect_without_changing_job(self):
        with patch('portal.baichuan_stream.monotonic', side_effect=[0,26]):
            stream=events(self.owner,self.job.pk); self.event(stream)
            self.assertTrue(self.event(stream)['done']['reconnect'])
        self.job.refresh_from_db(); self.assertEqual(self.job.status,'queued')

    def test_heartbeat_does_not_leak_private_checkpoint_document_or_model(self):
        self.update(checkpoint={'conditions':{'raw':'PRIVATE JSON'},'model_response':'SECRET','pending_attachment_ids':['PRIVATE']})
        with patch('portal.baichuan_stream.sleep'):
            stream=events(self.owner,self.job.pk); self.event(stream)
            self.assertEqual(self.event(stream),{'delta':''}); stream.close()

    def test_failed_cancelled_partial_and_awaiting_input_terminate_without_fake_success(self):
        for status in ('failed','cancelled','partial','awaiting_input'):
            self.update(status=status,error_code='synthetic_error')
            event=self.event(events(self.owner,self.job.pk))
            self.assertEqual(event['done']['job']['status'],status)

    def test_completed_reconnect_returns_only_existing_reply_and_no_duplicate(self):
        self.terminal()
        for _ in range(2):
            stream=events(self.owner,self.job.pk)
            self.assertIn('已确认 1', self.event(stream)['delta'])
            self.assertEqual(self.event(stream)['done']['job']['status'],'completed')
        self.assertEqual(BaichuanMessage.objects.count(),1)

    def test_real_session_logout_stops_open_stream(self):
        client=Client(); self.login(client,self.owner)
        response=client.post(self.path,data='{}',content_type='application/json')
        self.assertEqual(response.status_code,200)
        stream=iter(response.streaming_content); self.event(stream)
        Session.objects.filter(session_key=client.session.session_key).delete()
        self.terminal(text='PRIVATE AFTER LOGOUT')
        event=self.event(stream)
        self.assertEqual(event['error']['code'],'scope_revoked')
        self.assertNotIn('PRIVATE',json.dumps(event))

    def test_real_session_expiry_stops_open_stream(self):
        client=Client(); self.login(client,self.owner)
        response=client.post(self.path,data='{}',content_type='application/json')
        stream=iter(response.streaming_content); self.event(stream)
        Session.objects.filter(session_key=client.session.session_key).update(expire_date=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.event(stream)['error']['code'],'scope_revoked')

    def test_missing_user_identity_stops_open_stream(self):
        stream=events(self.owner,self.job.pk); self.event(stream)
        # Owner FKs protect real deletion. A stale principal that no longer
        # resolves must still fail closed rather than raising DoesNotExist.
        self.owner.pk += 1000000
        self.assertEqual(self.event(stream)['error']['code'],'scope_revoked')

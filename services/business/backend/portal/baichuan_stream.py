"""Read-only, bounded SSE observation of durable jobs; never execute work here."""
import json
from time import monotonic, sleep

from django.contrib.sessions.models import Session
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from .baichuan_assistant_models import BaichuanConversation, BaichuanMessage
from .baichuan_assistant_service import job_data, require_assistant
from .baichuan_jobs import job_for
from .baichuan_service import BaichuanError

WINDOW_SECONDS = 25
POLL_SECONDS = .25
ACTIVE = frozenset({'queued', 'running', 'cancel_requested'})
STAGES = {
    'parsing': '正在读取附件正文，未能识别的内容不会推测。\n',
    'planning': '正在理解需求，区分硬性要求、优先项和证书主体。\n',
    'matching': '检索条件已校验，正在按当前库资料逐项匹配。\n',
}


def frame(data):
    return ('data: ' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n\n').encode('utf-8')


def observed_job(user, identifier, session_key=None):
    row = job_for(user, identifier)
    require_assistant(user)
    if session_key is not None:
        session = Session.objects.filter(session_key=session_key, expire_date__gt=timezone.now()).first()
        data = session.get_decoded() if session else {}
        if (str(data.get('_auth_user_id')) != str(user.pk) or data.get('version') != user.session_version
                or not constant_time_compare(data.get('_auth_user_hash', ''), user.get_session_auth_hash())):
            raise BaichuanError('not_found', '任务不存在或不可访问。', 404)
    if row.kind != 'query' or not row.conversation_id:
        raise BaichuanError('not_found', '任务不存在或不可访问。', 404)
    revision = BaichuanConversation.objects.filter(pk=row.conversation_id, owner=user, scope=row.scope).values_list('condition_revision', flat=True).first()
    return row, revision == row.payload.get('condition_revision')


def events(user, identifier, session_key=None):
    """Reconnect observes fresh committed state, without replaying a model call.

    Only fixed stage descriptions and the fenced worker's public reply leave
    this generator. Checkpoint/model/document payloads never cross the wire.
    Closing the iterator has no job cancellation or persistence side effects.
    """
    deadline = monotonic() + WINDOW_SECONDS
    stages = set()
    try:
        while True:
            row, current = observed_job(user, identifier, session_key)
            if not current:
                yield frame({'done': {'job': job_data(row), 'superseded': True}})
                return
            if not stages and row.status in ACTIVE:
                stages.add('accepted')
                yield frame({'delta': '已接收本轮需求，任务在后台继续。\n'})
                continue  # Re-authorize after yielding before sending more data.
            if row.status in ACTIVE and row.stage in STAGES and row.stage not in stages:
                stages.add(row.stage)
                yield frame({'delta': STAGES[row.stage]})
                continue
            if row.status not in ACTIVE:
                reply = BaichuanMessage.objects.filter(conversation_id=row.conversation_id,
                    role='assistant', metadata__job_id=str(row.pk)).first()
                if reply:
                    # The worker bounds public summaries; no artificial token
                    # splitting or delayed playback of an already ready answer.
                    yield frame({'delta': reply.content[:4000]})
                    # A revoke or new turn between yields wins over completion.
                    row, current = observed_job(user, identifier, session_key)
                yield frame({'done': {'job': job_data(row), 'superseded': not current}})
                return
            if monotonic() >= deadline:
                yield frame({'done': {'job': job_data(row), 'reconnect': True}})
                return
            # Empty delta is a heartbeat compatible with the existing parser.
            yield frame({'delta': ''})
            sleep(POLL_SECONDS)
    except BaichuanError:
        yield frame({'error': {'code': 'scope_revoked', 'detail': '任务不存在或不可访问，请重新登录或检查权限。'}})

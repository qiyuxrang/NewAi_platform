"""Real OS process death against synthetic file SQLite; no target data or model."""
from datetime import datetime
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from django.core.management import call_command
from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from portal.baichuan_assistant_models import BaichuanJob, BaichuanJobItem
from portal.baichuan_jobs import claim_job, enqueue_job
from portal.baichuan_models import Company
from portal.models import ModelCallLog, Role, User


CHILD = r'''
import json,socket,sys,time
from pathlib import Path
backend,action,job_id,ready,expected_database=sys.argv[1:]
sys.path.insert(0,backend)
attempts={'socket':0,'DNS':0}
def denied(kind):
 def fail(*args,**kwargs):
  attempts[kind]+=1
  raise AssertionError('Synthetic process test denied '+kind)
 return fail
socket.create_connection=denied('socket')
socket.socket.connect=denied('socket')
socket.getaddrinfo=denied('DNS')
import django
django.setup()
from django.db import connection
from portal.baichuan_assistant_models import BaichuanJob,BaichuanJobItem
from portal.baichuan_jobs import claim_job,heartbeat,leased_job,save_item,save_job
from portal.baichuan_service import BaichuanError
from portal.baichuan_models import Company
from portal.models import ModelCallLog
assert Path(connection.settings_dict['NAME']).resolve()==Path(expected_database).resolve()
assert Company.objects.count()==0 and ModelCallLog.objects.count()==0
if action in ('committed','uncommitted'):
 row=claim_job('crash-worker-a',job_id=job_id,lease_seconds=5)
 assert row and row.fence==row.attempts==1
 save_job(row.pk,'crash-worker-a',row.fence,stage='matching',checkpoint={'next_item':1},counts={'processed':0})
 def signal():
  temporary=Path(ready).with_suffix('.tmp')
  temporary.write_text(json.dumps({'pid':__import__('os').getpid(),'fence':row.fence,'lease_expires_at':row.lease_expires_at.isoformat(),'action':action}),encoding='utf8')
  temporary.replace(ready)
 def idle():
  deadline=time.monotonic()+40
  while time.monotonic()<deadline:time.sleep(.05)
  raise AssertionError('Parent did not hard-stop the synthetic child')
 with leased_job(row.pk,'crash-worker-a',row.fence):
  save_item(row.pk,'crash-worker-a',row.fence,item_key='first',status='completed',checkpoint={'synthetic':True})
  save_job(row.pk,'crash-worker-a',row.fence,checkpoint={'next_item':2},counts={'processed':1})
  if action=='uncommitted':
   signal()
   idle()
 if action=='committed':
  signal()
  idle()
else:
 row=claim_job('crash-worker-b',job_id=job_id,lease_seconds=10)
 assert row and row.fence==row.attempts==2
 old={}
 for name,fn,kwargs in [
  ('heartbeat',heartbeat,{}),
  ('checkpoint',save_job,{'checkpoint':{'bad_old_worker':True}}),
  ('item',save_item,{'item_key':'stale','status':'completed'})]:
  try:fn(row.pk,'crash-worker-a',1,**kwargs)
  except BaichuanError as error:
   assert error.code=='stale_lease'
   old[name]=error.code
  else:raise AssertionError('Old fence unexpectedly wrote '+name)
 before={'checkpoint':row.checkpoint,'items':BaichuanJobItem.objects.filter(job=row).count()}
 with leased_job(row.pk,'crash-worker-b',row.fence):
  save_item(row.pk,'crash-worker-b',row.fence,item_key='first',status='completed',checkpoint={'synthetic':True})
  save_job(row.pk,'crash-worker-b',row.fence,status='completed',checkpoint={'next_item':2},counts={'processed':1},result_ref={'synthetic_item':'first'})
 assert claim_job('crash-worker-c',job_id=job_id) is None
 assert BaichuanJob.objects.filter(pk=job_id,status='completed').count()==1
 assert BaichuanJobItem.objects.filter(job_id=job_id).count()==1
 assert Company.objects.count()==0 and ModelCallLog.objects.count()==0
 assert attempts=={'socket':0,'DNS':0}
 print(json.dumps({'action':action,'before':before,'old_fence_rejected':old,'single_completion':True,'external_attempts':attempts}))
'''


class JobProcessCrashTests(TransactionTestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, "sqlite")
        self.database = str(connection.settings_dict["NAME"])
        self.assertFalse(self.database.startswith("file:"))
        self.assertNotEqual(self.database, ":memory:")
        self.assertIn("baichuan-checks", Path(self.database).parts)
        call_command("seed_portal", stdout=StringIO())
        self.owner = User.objects.create_user("synthetic-crash-owner", password="test-only",
                                              must_change_password=False)
        self.owner.roles.add(Role.objects.get(code="product"))
        config = override_settings(PORTAL_BAICHUAN_SCOPE_CONFIRMED=True,
            PORTAL_BAICHUAN_READ_USER_IDS=[self.owner.pk],
            PORTAL_BAICHUAN_WRITE_USER_IDS=[self.owner.pk],
            PORTAL_BAICHUAN_READ_ROLE_CODES=[], PORTAL_BAICHUAN_WRITE_ROLE_CODES=[],
            BAICHUAN_ASSISTANT_SCOPE="isolated")
        config.enable()
        self.addCleanup(config.disable)
        self.assertEqual(Company.objects.count(), 0)
        self.assertEqual(ModelCallLog.objects.count(), 0)

    def exercise_hard_death(self, action):
        job, created = enqueue_job(self.owner, kind="query", payload={"synthetic": True},
                                   idempotency_key="hard-death-" + action)
        self.assertTrue(created)
        environment = {key: value for key, value in os.environ.items() if key.upper() in {
            "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH", "LOCALAPPDATA", "USERPROFILE"}}
        environment.update(PORTAL_SECRET_KEY="synthetic-hard-death-only-not-deployment-20261018",
            PORTAL_DEBUG="1", PORTAL_HTTPS="0", PORTAL_SQLITE_PATH=self.database,
            PORTAL_BAICHUAN_SCOPE_CONFIRMED="1", PORTAL_BAICHUAN_ASSISTANT_SCOPE="isolated",
            PORTAL_BAICHUAN_READ_USER_IDS=str(self.owner.pk),
            PORTAL_BAICHUAN_WRITE_USER_IDS=str(self.owner.pk),
            PORTAL_BAICHUAN_READ_ROLE_CODES="", PORTAL_BAICHUAN_WRITE_ROLE_CODES="",
            DJANGO_SETTINGS_MODULE="config.settings", PYTHONIOENCODING="utf-8")
        backend = str(Path(__file__).resolve().parents[2])
        connection.close()
        process = None
        with tempfile.TemporaryDirectory(prefix="baichuan-hard-death-") as directory:
            ready = Path(directory) / "durable-ready.json"
            command = [sys.executable, "-X", "utf8", "-c", CHILD, backend, action,
                       str(job.pk), str(ready), self.database]
            try:
                process = subprocess.Popen(command, env=environment, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                deadline = time.monotonic() + 15
                while not ready.exists():
                    if process.poll() is not None:
                        output, error = process.communicate(timeout=2)
                        self.fail(error.decode(errors="replace") + output.decode(errors="replace"))
                    if time.monotonic() >= deadline:
                        self.fail("Synthetic worker did not reach its crash boundary")
                    time.sleep(.01)
                signal = json.loads(ready.read_text(encoding="utf8"))
                worker_pid = signal["pid"]
                self.assertIsInstance(worker_pid, int)
                if worker_pid != process.pid:
                    # Windows venv python.exe can redirect to an immediate child.
                    # Prove the exact parent and unique test arguments before killing it.
                    self.assertEqual(os.name, "nt")
                    identity = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive",
                        "-Command", "Get-CimInstance Win32_Process -Filter 'ProcessId = "
                        + str(worker_pid) + "' | Select-Object ProcessId,ParentProcessId,CommandLine | ConvertTo-Json -Compress"],
                        capture_output=True, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    self.assertEqual(identity.returncode, 0, identity.stderr.decode(errors="replace"))
                    verified = json.loads(identity.stdout)
                    self.assertEqual(verified["ProcessId"], worker_pid)
                    self.assertEqual(verified["ParentProcessId"], process.pid)
                    self.assertIn(str(ready), verified["CommandLine"])
                    self.assertIn(str(job.pk), verified["CommandLine"])
                # No graceful shutdown signal or Python finally: TerminateProcess on Windows,
                # SIGKILL on POSIX. Only this exact newly-created test process is killed.
                if worker_pid == process.pid:
                    process.kill()
                else:
                    os.kill(worker_pid, 15)  # Windows SIGTERM uses TerminateProcess.
                output, error = process.communicate(timeout=10)
                self.assertNotEqual(process.returncode, 0)
                self.assertEqual(error, b"")
                self.assertEqual(output, b"")
                job.refresh_from_db()
                self.assertEqual(job.status, "running")
                self.assertEqual((job.fence, job.attempts), (1, 1))
                expected_items = 1 if action == "committed" else 0
                self.assertEqual(job.checkpoint, {"next_item": 2 if expected_items else 1})
                self.assertEqual(job.counts["processed"], expected_items)
                self.assertEqual(BaichuanJobItem.objects.filter(job=job).count(), expected_items)
                # Use real elapsed wall time; never rewrite lease_expires_at to manufacture recovery.
                expiry = datetime.fromisoformat(signal["lease_expires_at"])
                if timezone.now() < expiry:
                    self.assertIsNone(claim_job("premature-worker", job_id=job.pk))
                deadline = time.monotonic() + 7
                while timezone.now() <= expiry:
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(.02)
                connection.close()
                recovery = subprocess.run([*command[:6], "recover", str(job.pk), str(ready), self.database],
                    env=environment, capture_output=True, timeout=20,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                self.assertEqual(recovery.returncode, 0, recovery.stderr.decode(errors="replace"))
                proof = json.loads(recovery.stdout)
                self.assertEqual(proof["before"], {
                    "checkpoint": {"next_item": 2 if expected_items else 1}, "items": expected_items})
                self.assertTrue(proof["single_completion"])
                self.assertEqual(len(proof["old_fence_rejected"]), 3)
                job.refresh_from_db()
                self.assertEqual((job.status, job.fence, job.attempts), ("completed", 2, 2))
                self.assertEqual(job.checkpoint, {"next_item": 2})
                self.assertEqual(job.counts["processed"], 1)
                self.assertIsNone(job.lease_expires_at)
                self.assertEqual(job.lease_owner, "")
                self.assertEqual(BaichuanJob.objects.count(), 1)
                self.assertEqual(BaichuanJobItem.objects.filter(job=job).count(), 1)
                self.assertEqual(Company.objects.count(), 0)
                self.assertEqual(ModelCallLog.objects.count(), 0)
                print("PROCESS_CRASH_PROOF " + json.dumps({
                    "case": action, "killed_pid": worker_pid, "launcher_pid": process.pid,
                    "exitcode": process.returncode,
                    "lease_naturally_expired": True, "recovery": proof}))
            finally:
                if process is not None and process.poll() is None:
                    process.kill()
                    process.communicate(timeout=10)
                connection.close()

    def test_hard_process_death_recovers_committed_checkpoint_without_duplicate_item(self):
        self.exercise_hard_death("committed")

    def test_hard_process_death_rolls_back_inflight_atomic_checkpoint_and_item(self):
        self.exercise_hard_death("uncommitted")

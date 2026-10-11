"""Bound Linux Office subprocesses to a session owned by this invocation."""

import os
from pathlib import Path
import signal
import subprocess
import time


def _session_members(session_id, proc_root=Path("/proc")):
    """Read Linux identities, including descendants whose launcher exited."""
    members = {}
    for directory in proc_root.iterdir():
        if not directory.name.isdecimal():
            continue
        try:
            fields = (directory / "stat").read_bytes().decode("utf-8", errors="replace").rsplit(")", 1)[1].split()
            if int(fields[3]) == session_id:
                members[int(directory.name)] = fields[19]  # Kernel start time.
        except (OSError, ValueError, IndexError):
            continue
    return members


def _signal_session_members(session_id, sig):
    if session_id == os.getsid(0):
        raise RuntimeError("Refusing to signal the caller's session")
    members = _session_members(session_id)
    for pid, started in members.items():
        descriptor = None
        try:
            # Pin the process before the identity check; never signal a reused PID.
            descriptor = os.pidfd_open(pid)
            if _session_members(session_id).get(pid) == started:
                signal.pidfd_send_signal(descriptor, sig)
        except ProcessLookupError:
            continue
        finally:
            if descriptor is not None:
                os.close(descriptor)
    return bool(members)


def _cleanup_session(session_id):
    if not _signal_session_members(session_id, signal.SIGTERM):
        return
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if not _session_members(session_id):
            return
        time.sleep(0.05)
    _signal_session_members(session_id, signal.SIGKILL)


def run_office(command, *, linux, **options):
    """Keep the established Word path; Linux gets owned-session cleanup.

    Linux children keep this session even when using separate process groups.
    The renderer handles TERM for reports/profile cleanup. This final sweep also
    handles a stuck or abruptly terminated supervisor without touching a shared
    listener or any process outside the freshly created session.
    """
    if not linux:
        return subprocess.run(command, **options)
    if not sys_platform_linux() or not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        raise OSError("LibreOffice requires Linux with pidfd process isolation")
    timeout = options.pop("timeout")
    options.pop("capture_output", None)
    options.pop("creationflags", None)
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True, **options)
    try:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                _cleanup_session(process.pid)
                process.wait(timeout=5)
            raise
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    finally:
        _cleanup_session(process.pid)
        if process.poll() is None:
            process.wait(timeout=5)


def sys_platform_linux():
    import sys
    return sys.platform.startswith("linux")

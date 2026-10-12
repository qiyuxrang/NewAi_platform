"""Keep a task lease alive while model, Chromium and Office calls are blocking."""
from contextlib import contextmanager
from threading import Event, Thread

from django.conf import settings
from django.db import OperationalError, close_old_connections, connections


@contextmanager
def lease_heartbeat(task_id, fence):
    stopped = Event()

    def beat():
        from .product_worker import _renew
        interval = max(1, min(30, settings.PRODUCT_LEASE_SECONDS // 3))
        try:
            while not stopped.wait(interval):
                close_old_connections()
                try:
                    _renew(task_id, fence)
                except OperationalError:
                    # A short database lock is not permission to steal or extend an expired lease.
                    close_old_connections()
                except Exception:
                    return
        finally:
            connections.close_all()

    thread = Thread(target=beat, name="product-lease-heartbeat", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=5)

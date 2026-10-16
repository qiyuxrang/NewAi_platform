"""Serialize short task/gateway writes within one worker process."""
from contextlib import contextmanager
from threading import RLock

from django.db import transaction


# Cross-process correctness remains owned by DB locks, task fences and leases.
# ponytail: one process-wide SQLite write lock; remove it after moving all writes to PostgreSQL row locks.
db_lock = RLock()


@contextmanager
def atomic():
    with db_lock, transaction.atomic():
        yield

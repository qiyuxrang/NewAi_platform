import time
import uuid

from django.core.management.base import BaseCommand, CommandError

from portal.baichuan_assistant_worker import run_one


class Command(BaseCommand):
    help = "Process durable Baichuan assistant jobs independently of the browser."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--poll-seconds", type=float, default=1)

    def handle(self, *args, **options):
        if not 0.1 <= options["poll_seconds"] <= 30:
            raise ValueError("poll-seconds must be between 0.1 and 30")
        worker_id = "baichuan-" + str(uuid.uuid4())
        while True:
            try:
                worked = run_one(worker_id)
            except Exception:
                # Persisted jobs carry a sanitized error code; never print a
                # provider response or private attachment into the service log.
                if options["once"]:
                    raise CommandError("Baichuan job failed; inspect its persisted error code.") from None
                self.stderr.write("Baichuan job failed; continuing other queued jobs.")
                worked = False
            if options["once"]:
                return
            if not worked:
                time.sleep(options["poll_seconds"])

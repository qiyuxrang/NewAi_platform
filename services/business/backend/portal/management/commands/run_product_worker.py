import logging
import sqlite3
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, close_old_connections

from portal.product_worker import run_once


class Command(BaseCommand):
    help = "运行产品P1持久任务执行器；不启用模型许可时不会外发资料。"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        if not settings.PRODUCT_P1_ENABLED:
            raise CommandError("产品P1未启用，请使用获准的隔离环境。")
        retry_delay = 1
        while True:
            try:
                worked = run_once()
            except OperationalError as error:
                cause = error.__cause__
                code = getattr(cause, "sqlite_errorcode", None)
                if options["once"] or not (isinstance(cause, sqlite3.OperationalError)
                        and type(code) is int and (code & 0xFF) in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}):
                    raise
                close_old_connections()
                logging.getLogger(__name__).warning("Product worker SQLite lock code=%d; retrying in %ds", code, retry_delay)
                time.sleep(retry_delay)
                retry_delay = min(5, retry_delay * 2)
                continue
            retry_delay = 1
            if options["once"]:
                self.stdout.write("已处理一次领取。" if worked else "暂无可执行任务。")
                return
            if not worked:
                time.sleep(2)

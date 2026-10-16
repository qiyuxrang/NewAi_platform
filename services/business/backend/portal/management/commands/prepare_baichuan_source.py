"""Prepare private source materials; never imports or confirms a manifest."""
import json

from django.core.management.base import BaseCommand, CommandError

from portal.baichuan_source import prepare_source


class Command(BaseCommand):
    help = "将明确指定的私人源数据转换为初始化模板JSON行及映射；无数据库写入。"

    def add_arguments(self, parser):
        for name in ("companies", "claims", "facts", "audit", "output-dir"):
            parser.add_argument("--" + name, required=True)

    def handle(self, *args, **options):
        try:
            report = prepare_source(*(options[key] for key in ("companies", "claims", "facts", "audit", "output_dir")))
        except (ValueError, OSError, KeyError, TypeError) as error:
            raise CommandError(str(error)) from error
        self.stdout.write(json.dumps({key: value for key, value in report.items() if key not in {"claim_decisions", "company_row_ids", "source_claims", "source_facts"}}, ensure_ascii=False, indent=2))

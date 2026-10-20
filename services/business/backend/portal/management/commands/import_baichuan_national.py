import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from portal.baichuan_national_import import apply_catalog, preview_catalog
from portal.baichuan_service import BaichuanError
from portal.models import User


class Command(BaseCommand):
    help = "全国名录增量维护：默认只读预检；--apply须明确确认清单及现有维护账号。"

    def add_arguments(self, parser):
        parser.add_argument("--input", required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--manifest")
        parser.add_argument("--actor")
        parser.add_argument("--report", required=True)

    def handle(self, *args, **options):
        target = Path(options["report"]).resolve()
        source = Path(options["input"]).resolve()
        protected = [source] + ([Path(options["manifest"]).resolve()] if options.get("manifest") else [])
        if target in protected or target.exists() and any(item.exists() and target.samefile(item) for item in protected):
            raise CommandError("报告路径不能覆盖输入或确认清单")
        committed, temporary = False, None
        try:
            if options["apply"]:
                if not options["manifest"] or not options["actor"]:
                    raise CommandError("--apply须提供--manifest与--actor")
                manifest = json.loads(Path(options["manifest"]).read_text(encoding="utf-8-sig"))
                actor = User.objects.get(username=options["actor"], is_active=True, must_change_password=False)
                result = apply_catalog(source, manifest, actor)
                committed = result["database_status"] == "committed"
            else:
                result = preview_catalog(source)
                result["database_status"] = "unchanged"
            target.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, prefix=target.name + ".", suffix=".tmp", delete=False) as output:
                temporary = Path(output.name)
                json.dump(result, output, ensure_ascii=False, indent=2)
                output.write("\n")
            temporary.replace(target)
        except (BaichuanError, ValueError, OSError, KeyError, IndexError, TypeError, BadZipFile, ParseError, DatabaseError, User.DoesNotExist) as error:
            if temporary:
                temporary.unlink(missing_ok=True)
            state = "数据库已提交但报告未写入，保留清单后重放核对" if committed else "数据库未写入或事务已回滚"
            raise CommandError(f"{state}：{error}") from error
        # Business/source content belongs only in the private report.
        self.stdout.write(json.dumps({"mode": result["mode"], "database_status": result["database_status"],
                                      "counts": result["counts"], "report": str(target)}, ensure_ascii=False))

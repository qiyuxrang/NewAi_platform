import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import BadZipFile
from xml.etree.ElementTree import ParseError

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from portal.baichuan_import import apply_import, preview_import
from portal.baichuan_service import BaichuanError
from portal.models import User


class Command(BaseCommand):
    help = "百川阁一次性初始化：默认只读预检；apply须确认清单及已配置的维护权限。"

    def add_arguments(self, parser):
        parser.add_argument("--input", required=True)
        modes = parser.add_mutually_exclusive_group()
        modes.add_argument("--dry-run", action="store_true")
        modes.add_argument("--apply", action="store_true")
        parser.add_argument("--mapping", help="明确列名/人员/现有公司映射及备注归一JSON")
        parser.add_argument("--manifest", help="已人工确认 confirmed=true 的预检报告")
        parser.add_argument("--actor", help="apply的已有维护者用户名；不改变账号授权")
        parser.add_argument("--report", required=True)

    def handle(self, *args, **options):
        committed, result, failure = False, None, None
        target = Path(options["report"]).resolve()
        try:
            source = Path(options["input"]).resolve(strict=True)
            protected = [source] + [Path(options[key]).resolve() for key in ("mapping", "manifest") if options.get(key)]
            if target in protected or target.exists() and any(target.samefile(item) for item in protected if item.exists()):
                raise CommandError("报告路径不能覆盖原表、映射或确认清单")
            mapping = json.loads(Path(options["mapping"]).read_text(encoding="utf-8-sig")) if options["mapping"] else None
            if options["apply"]:
                if not options["manifest"] or not options["actor"]:
                    raise CommandError("apply须提供 --manifest 与 --actor")
                manifest = json.loads(Path(options["manifest"]).read_text(encoding="utf-8-sig"))
                actor = User.objects.get(username=options["actor"], is_active=True, must_change_password=False)
                result = apply_import(source, manifest, actor, mapping)
                committed = True
            else:
                result = preview_import(source, mapping)
                result["database_status"] = "unchanged"
        except (BaichuanError, ValueError, OSError, KeyError, IndexError, TypeError, BadZipFile, ParseError, DatabaseError, User.DoesNotExist) as error:
            failure = str(error)
            result = {"mode": "apply" if options["apply"] else "dry_run", "database_status": "rolled_back" if options["apply"] else "unchanged",
                      "code": getattr(error, "code", "import_failed"), "detail": failure, "errors": getattr(error, "errors", None)}
        if result is None:
            return
        serialized = json.dumps(result, ensure_ascii=False, indent=2)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, prefix=target.name + ".", suffix=".tmp", delete=False) as output:
                temporary = Path(output.name)
                output.write(serialized + "\n")
            temporary.replace(target)
        except OSError as error:
            if "temporary" in locals():
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
            state = "数据库已提交，回执未生成；请保留原确认清单重跑，不能宣称已回滚" if committed else "数据库未写入"
            raise CommandError(f"{state}；报告写入失败：{error}") from error
        self.stdout.write(serialized)
        if failure:
            raise CommandError(failure)

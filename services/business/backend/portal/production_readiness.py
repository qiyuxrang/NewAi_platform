"""Read-only production configuration checks without disclosing secrets."""
import os
import platform
import re
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from django.db import connection


def _item(code, state, message):
    return {"code": code, "state": state, "message": message}


def _service_url(value, allowlist, *, loopback_http=False, paths=("", "/")):
    try:
        parsed = urlsplit(value)
        return (isinstance(value, str) and isinstance(allowlist, (list, tuple))
                and value in allowlist and bool(parsed.hostname) and parsed.port != 0
                and not parsed.username and not parsed.password and not parsed.query
                and not parsed.fragment and (paths is None or parsed.path in paths)
                and not any(ord(char) < 33 or ord(char) > 126 for char in value)
                and "\\" not in value and "%" not in value
                and not any(part in (".", "..") for part in parsed.path.split("/"))
                and (parsed.scheme == "https" or (loopback_http and parsed.scheme == "http"
                     and parsed.hostname in {"127.0.0.1", "::1"})))
    except (TypeError, ValueError):
        return False


def _local_path(value, *, directory=False):
    try:
        path = Path(value)
        return path.is_absolute() and not path.is_symlink() and (path.is_dir() if directory else path.is_file())
    except (TypeError, ValueError, OSError):
        return False


def _feature_checks(configured, environment):
    """Configuration/local existence only: never connect or execute dependencies."""
    checks = []
    if getattr(configured, "AGENT_PLATFORM_ENABLED", False):
        url = getattr(configured, "AGENT_RUNTIME_URL", "")
        token = getattr(configured, "AGENT_RUNTIME_SERVICE_TOKEN", "")
        ready = _service_url(url, getattr(configured, "AGENT_RUNTIME_ALLOWED_URLS", ()))
        checks.append(_item("agent_runtime_identity", "passed" if ready and isinstance(token, str)
                            and len(token) >= 40 and all(33 <= ord(char) <= 126 for char in token) else "blocked",
                            "Agent 生产连接必须使用允许名单内 HTTPS 地址和有效服务身份。"))
        presets = getattr(configured, "AGENT_RUNTIME_MODEL_PRESETS", {})
        bundles = [presets] if isinstance(presets, dict) and "main" in presets else (
            list(presets.values()) if isinstance(presets, dict) else [])
        presets_ready = bool(bundles) and all(isinstance(bundle, dict) and all(
            isinstance(bundle.get(name), dict) and set(bundle[name]) == {"route_code", "selection"}
            and isinstance(bundle[name]["route_code"], str) and bool(bundle[name]["route_code"])
            for name in ("main", "researcher", "reviewer")) for bundle in bundles)
        checks.append(_item("agent_model_presets", "passed" if presets_ready else "blocked",
                            "主运行及两个子能力需配置获准模型预设；配置不证明真实模型不同或可用。"))
        checks.append(_item("agent_production_topology", "passed" if environment.get(
            "PORTAL_AGENT_DEPLOYMENT_MODE") in {"single_host", "helm_kubernetes"} else "blocked",
            "启用 Agent 须明确选择 single_host 或 helm_kubernetes；声明部署方式不证明执行器已部署。"))
        # Portal must not receive the runtime's license or database credentials.
        # Only a separate runtime preflight can establish actual entitlement.
        checks.extend([
            _item("agent_runtime_license", "external_gate", "须独立验证原生 Runtime 许可及自定义认证授权；不以密钥存在替代验收。"),
            _item("agent_runtime_persistence", "external_gate", "须验证所选部署的持久化、强杀恢复和队列排空；多副本部署另须验证跨副本协调。"),
            _item("agent_isolation_and_limits", "external_gate", "AG-15/16 完整出口必须通过后才可使用真实资料。"),
        ])
        for code, attribute in (("agent_product_storage", "PRODUCT_STORAGE_ROOT"),
                                ("agent_hr_storage", "HR_STORAGE_ROOT")):
            checks.append(_item(code, "passed" if _local_path(getattr(configured, attribute, None), directory=True) else "blocked",
                                "Agent 与领域 Worker 必须共享已部署私有存储；目录存在不证明持久化或恢复。"))
    model_calls = getattr(configured, "PRODUCT_MODEL_CALLS_ALLOWED", False)
    formal_release = getattr(configured, "PRODUCT_FORMAL_RELEASE_ENABLED", False)
    office_render = getattr(configured, "PRODUCT_OFFICE_RENDER_ENABLED", False)
    if model_calls:
        checks.append(_item("product_parser_runtime", "passed" if _local_path(
            getattr(configured, "PRODUCT_PARSER_PYTHON", None)) else "blocked",
            "启用产品模型生成需部署受信资料解析 Python 运行时。"))
    if model_calls or formal_release or office_render:
        checks.append(_item("product_document_runtime", "passed" if _local_path(
            getattr(configured, "PRODUCT_DOCUMENT_PYTHON", None)) else "blocked",
            "启用产品生成、正式发布或 Office 渲染需部署受信文档 Python 运行时。"))
        checks.append(_item("product_formal_quality", "external_gate", "真实正式三件套、Office 渲染及内容质量须独立验收；不新增成稿审批。"))
    if formal_release:
        checks.append(_item("product_formal_office_enabled", "passed" if office_render else "blocked",
                            "正式发布必须显式启用真实 Office 渲染；结构生成结果不能替代正式三件套验收。"))
    if formal_release or office_render:
        # File existence is configuration evidence only, never render acceptance.
        renderer = getattr(configured, "PRODUCT_OFFICE_RENDERER", "word")
        available = (platform.system() == "Windows" if renderer == "word" else
                     renderer == "libreoffice" and platform.system() == "Linux"
                     and all(_local_path(getattr(configured, name, None)) for name in
                         ("PRODUCT_LIBREOFFICE_EXECUTABLE", "PRODUCT_UNO_PYTHON")))
        checks.append(_item("product_office_platform", "passed" if available else "blocked",
                            "文档渲染需部署所选 Word 或 LibreOffice 运行时；文件存在仍需真实排版验收。"))
        checks.append(_item("product_office_acceptance", "external_gate",
                            "须独立验证目标执行者的 Word/PPT 实际渲染、许可、受支持运行方式、任务路由及私有文件；Windows 路径存在不证明可用。"))
    if environment.get("PORTAL_ENGINEERING_ENABLED") == "1":
        python = getattr(configured, "ENGINEERING_PYTHON", environment.get("PORTAL_ENGINEERING_PYTHON"))
        cli = getattr(configured, "ENGINEERING_COST_CLI", environment.get("PORTAL_ENGINEERING_COST_CLI"))
        checks.append(_item("engineering_runtime", "passed" if _local_path(python) and _local_path(cli) else "blocked",
                            "启用工程任务需由工程负责人提供受信 Python/CLI；平台不模拟成本算法。"))
        root = getattr(configured, "ENGINEERING_STORAGE_ROOT", environment.get("PORTAL_ENGINEERING_STORAGE_ROOT"))
        checks.append(_item("engineering_storage", "passed" if _local_path(root, directory=True) else "blocked",
                            "启用工程任务需明确私有共享持久目录，不能依赖容器可写层。"))
        checks.append(_item("engineering_business_acceptance", "external_gate", "工程接口、算法结果与持久卷须由工程负责人联合验收。"))
    for code, enabled, prefix in (
        ("product_retrieval", getattr(configured, "PRODUCT_RETRIEVAL_ENABLED", False), "PRODUCT_RETRIEVAL"),
        ("product_knowledge", getattr(configured, "PRODUCT_KNOWLEDGE_ENABLED", False), "PRODUCT_KNOWLEDGE"),
    ):
        if enabled:
            url = getattr(configured, prefix + "_URL", "")
            ready = _service_url(url, getattr(configured, prefix + "_ALLOWED_URLS", ()),
                                 paths=("/api/v1/retrieval",) if code == "product_knowledge" else None)
            ready = ready and urlsplit(url).port in (None, 443)
            token_name = getattr(configured, prefix + "_TOKEN_ENV", "")
            token = (environment.get(token_name, "") if isinstance(token_name, str)
                     and re.fullmatch(r"[A-Z][A-Z0-9_]{2,127}", token_name) else "")
            ready = (ready and isinstance(token, str) and 20 <= len(token) <= 512
                     and all(33 <= ord(char) <= 126 for char in token))
            checks.append(_item(code + "_identity", "passed" if ready else "blocked",
                                "启用知识/检索服务需明确 HTTPS 允许地址及服务令牌。"))
            checks.append(_item(code + "_acceptance", "external_gate", "真实知识服务权限、撤权及来源引用须独立验收。"))
    return checks


def evaluate_configuration(*, configured=settings, database_vendor=None, enabled_routes=None,
                           environment=None):
    """Return stable, machine-readable checks; never include configured values."""
    vendor = database_vendor or connection.vendor
    checks = []
    checks.append(_item("debug_disabled", "passed" if not configured.DEBUG else "blocked",
                        "调试模式已关闭。" if not configured.DEBUG else "生产环境必须关闭调试模式。"))
    checks.append(_item("https_enabled", "passed" if configured.HTTPS else "blocked",
                        "HTTPS安全策略已启用。" if configured.HTTPS else "生产环境必须启用HTTPS安全策略。"))
    checks.append(_item("postgresql", "passed" if vendor == "postgresql" else "blocked",
                        "使用PostgreSQL。" if vendor == "postgresql" else "生产环境必须使用PostgreSQL。"))
    secret_ready = isinstance(configured.SECRET_KEY, str) and len(configured.SECRET_KEY) >= 40
    checks.append(_item("secret_key", "passed" if secret_ready else "blocked",
                        "平台密钥长度符合要求。" if secret_ready else "平台密钥缺失或长度不足。"))
    hosts = configured.ALLOWED_HOSTS
    hosts_ready = bool(hosts) and all(isinstance(host, str) and host.strip() and host != "*" for host in hosts)
    checks.append(_item("allowed_hosts", "passed" if hosts_ready else "blocked",
                        "主机允许名单已明确配置。" if hosts_ready else "必须配置明确主机名，禁止空值和通配符。"))
    origins = configured.CSRF_TRUSTED_ORIGINS
    origins_ready = bool(origins) and all(
        isinstance(value, str) and urlsplit(value).scheme == "https" and bool(urlsplit(value).hostname)
        for value in origins
    )
    checks.append(_item("csrf_origins", "passed" if origins_ready else "blocked",
                        "CSRF可信来源均使用HTTPS。" if origins_ready else "必须配置至少一个HTTPS CSRF可信来源。"))

    if enabled_routes is None:
        from .models import ModelRoute
        enabled_routes = list(ModelRoute.objects.select_related("model__provider").filter(enabled=True))
    routes = list(enabled_routes)
    gateway_url = getattr(configured, "MODEL_GATEWAY_URL", "")
    gateway_token = getattr(configured, "MODEL_GATEWAY_TOKEN", "")
    gateway_allowlist = getattr(configured, "MODEL_GATEWAY_ALLOWED_URLS", ())
    from .model_gateway import validate_gateway_configuration
    gateway_ready = validate_gateway_configuration(gateway_url, gateway_token, gateway_allowlist)
    route_configs_ready = all(route.model.enabled and route.model.provider.enabled for route in routes)
    if routes:
        checks.append(_item("model_gateway", "passed" if gateway_ready else "external_gate",
                            "模型网关服务身份和地址已配置。" if gateway_ready
                            else "已有启用业务路由，但真实模型网关地址或服务令牌尚未配置。"))
        checks.append(_item("model_routes", "passed" if route_configs_ready else "blocked",
                            "启用路由对应的模型和服务商均已启用。" if route_configs_ready
                            else "存在指向停用模型或停用服务商的业务路由。"))
    else:
        checks.append(_item("model_gateway", "external_gate", "尚未启用任何真实业务模型路由。"))
        checks.append(_item("model_routes", "external_gate", "需要管理员在真实模型验证后启用业务路由。"))

    checks.extend(_feature_checks(configured, os.environ if environment is None else environment))
    blockers = [item["code"] for item in checks if item["state"] == "blocked"]
    external_gates = [item["code"] for item in checks if item["state"] == "external_gate"]
    return {
        "status": "blocked" if blockers else "external_gates" if external_gates else "ready",
        "checks": checks,
        "blockers": blockers,
        "external_gates": external_gates,
        "scope": "configuration_only_no_network_calls",
        "release_approved": False,
        "required_verifications": ["worker_liveness_and_shared_storage", "database_and_file_consistent_restore",
                                   "migration_rehearsal", "full_business_acceptance", "capacity_and_fault_acceptance"],
    }

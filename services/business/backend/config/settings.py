import os
import json
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from .database import postgres_database

BASE_DIR = Path(__file__).resolve().parents[2]
SECRET_KEY = os.environ.get("PORTAL_SECRET_KEY", "")
if len(SECRET_KEY) < 40:
    raise ImproperlyConfigured("请设置至少40字符的 PORTAL_SECRET_KEY")
DEBUG = os.environ.get("PORTAL_DEBUG") == "1"
HTTPS = os.environ.get("PORTAL_HTTPS", "1") == "1"
if not DEBUG and not HTTPS:
    raise ImproperlyConfigured("非调试环境必须启用 HTTPS")
ALLOWED_HOSTS = os.environ.get("PORTAL_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
CSRF_TRUSTED_ORIGINS = list(filter(None, os.environ.get("PORTAL_CSRF_TRUSTED_ORIGINS", "").split(",")))
INSTALLED_APPS = ["django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles", "rest_framework", "portal"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware", "whitenoise.middleware.WhiteNoiseMiddleware", "django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware", "portal.middleware.SessionPolicyMiddleware", "portal.ops_metrics.ApiMetricsMiddleware", "django.contrib.messages.middleware.MessageMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware"]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [BASE_DIR / "backend" / "templates"], "APP_DIRS": True, "OPTIONS": {"context_processors": ["django.template.context_processors.request", "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages"]}}]
if os.environ.get("PORTAL_DB_NAME"):
    DATABASES = {"default": postgres_database(name=os.environ["PORTAL_DB_NAME"],
        user=os.environ["PORTAL_DB_USER"], password=os.environ["PORTAL_DB_PASSWORD"],
        host=os.environ.get("PORTAL_DB_HOST", "db"), port=os.environ.get("PORTAL_DB_PORT", "5432"))}
else:
    if not DEBUG:
        raise ImproperlyConfigured("正式配置必须使用独立 PostgreSQL")
    database_path = Path(os.environ.get("PORTAL_SQLITE_PATH", str(BASE_DIR / ".runtime" / "portal.sqlite3")))
    if not database_path.is_absolute():
        database_path = BASE_DIR / database_path
    database_path.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the write lock before atomic read/write work; DEFERRED upgrades can
    # fail immediately despite busy_timeout when another writer is waiting.
    # ponytail: SQLite serializes transactions; use PostgreSQL for sustained concurrent writes.
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": database_path,
                              "OPTIONS": {"timeout": 30, "transaction_mode": "IMMEDIATE"}}}
AUTH_USER_MODEL = "portal.User"
AUTH_PASSWORD_VALIDATORS = [{"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"}, {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}}, {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"}, {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"}]
LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
_frontend_dist = Path(os.environ.get("PORTAL_FRONTEND_DIST", BASE_DIR / "frontend" / "dist"))
PORTAL_FRONTEND_DIST = _frontend_dist if _frontend_dist.is_absolute() else BASE_DIR / _frontend_dist
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_NAME = "enterprise_portal_session"
CSRF_COOKIE_NAME = "enterprise_portal_csrf"
SESSION_COOKIE_SECURE = HTTPS
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 28800
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
CSRF_COOKIE_SECURE = HTTPS
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_FAILURE_VIEW = "portal.views.csrf_failure"
SECURE_SSL_REDIRECT = HTTPS
SECURE_HSTS_SECONDS = 31536000 if HTTPS else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = HTTPS
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "no-referrer"
if os.environ.get("PORTAL_BEHIND_PROXY") == "1":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
LOGIN_URL = "/login"
DATA_UPLOAD_MAX_MEMORY_SIZE = 65536
REST_FRAMEWORK = {"DEFAULT_AUTHENTICATION_CLASSES": ["portal.authentication.PortalSessionAuthentication"], "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"], "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"]}
TRUSTED_MODULE_ORIGINS = list(filter(None, os.environ.get("PORTAL_TRUSTED_MODULE_ORIGINS", "").split(",")))
BUSINESS_SUMMARY_URL = os.environ.get("PORTAL_BUSINESS_SUMMARY_URL", "")
INTEGRATION_SECRET = os.environ.get("PORTAL_INTEGRATION_SECRET", "")
LOGIN_ATTEMPT_LIMIT = 5
LOGIN_IP_LIMIT = 30
LOGIN_WINDOW_SECONDS = 900
TICKET_TTL_SECONDS = 30
MODEL_GATEWAY_URL = os.environ.get("PORTAL_MODEL_GATEWAY_URL", "")
MODEL_GATEWAY_TOKEN = os.environ.get("PORTAL_MODEL_GATEWAY_TOKEN", "")
MODEL_GATEWAY_ALLOWED_URLS = tuple(filter(None, os.environ.get("PORTAL_MODEL_GATEWAY_ALLOWED_URLS", "http://127.0.0.1:18410,http://model-gateway:18410").split(",")))
MODEL_PROVIDER_LOCAL_HTTP = os.environ.get("PORTAL_MODEL_PROVIDER_LOCAL_HTTP") == "1"
try:
    MODEL_MAX_PENDING_PER_MODEL = int(os.environ.get("PORTAL_MODEL_MAX_PENDING_PER_MODEL", "4"))
except ValueError:
    raise ImproperlyConfigured("模型并发上限必须为整数") from None
if not 1 <= MODEL_MAX_PENDING_PER_MODEL <= 100:
    raise ImproperlyConfigured("模型并发上限必须位于1至100之间")
PRODUCT_P1_ENABLED = os.environ.get("PORTAL_PRODUCT_P1_ENABLED") == "1"
# Baichuan stays closed until the deployment's shared scope is explicitly set.
PORTAL_BAICHUAN_SCOPE_CONFIRMED = os.environ.get("PORTAL_BAICHUAN_SCOPE_CONFIRMED") == "1"
BAICHUAN_ASSISTANT_ENABLED = os.environ.get("PORTAL_BAICHUAN_ASSISTANT_ENABLED") == "1"
BAICHUAN_ASSISTANT_SCOPE = os.environ.get("PORTAL_BAICHUAN_ASSISTANT_SCOPE", "default")
BAICHUAN_ASSISTANT_LOCAL_GRAMMAR = os.environ.get("PORTAL_BAICHUAN_ASSISTANT_LOCAL_GRAMMAR") == "1"
BAICHUAN_ASSISTANT_UNLIMITED_QUERY_MODELS = os.environ.get("PORTAL_BAICHUAN_ASSISTANT_UNLIMITED_QUERY_MODELS") == "1"
BAICHUAN_TRUST_LEGACY_QUALIFICATIONS = os.environ.get("PORTAL_BAICHUAN_TRUST_LEGACY_QUALIFICATIONS") == "1"
BAICHUAN_ASSISTANT_MODEL_ROUTE = os.environ.get("PORTAL_BAICHUAN_ASSISTANT_MODEL_ROUTE", "product_assistant")
BAICHUAN_STORAGE_ROOT = Path(os.environ.get("PORTAL_BAICHUAN_STORAGE_ROOT", BASE_DIR / ".runtime" / "baichuan-private"))
BAICHUAN_RESEARCH_ENABLED = os.environ.get("PORTAL_BAICHUAN_RESEARCH_ENABLED") == "1"
BAICHUAN_FACT_WRITE_ENABLED = os.environ.get("PORTAL_BAICHUAN_FACT_WRITE_ENABLED") == "1"
BAICHUAN_ENVIRONMENT_LABEL = os.environ.get("PORTAL_BAICHUAN_ENVIRONMENT_LABEL", "")
BAICHUAN_DATASET_KIND = os.environ.get("PORTAL_BAICHUAN_DATASET_KIND", "unconfirmed")
BAICHUAN_TARGET_DATASET_CONFIRMED = os.environ.get("PORTAL_BAICHUAN_TARGET_DATASET_CONFIRMED") == "1"
BAICHUAN_TARGET_BACKUP_REF = os.environ.get("PORTAL_BAICHUAN_TARGET_BACKUP_REF", "")
PORTAL_BAICHUAN_READ_USER_IDS = tuple(filter(None, os.environ.get("PORTAL_BAICHUAN_READ_USER_IDS", "").split(",")))
PORTAL_BAICHUAN_WRITE_USER_IDS = tuple(filter(None, os.environ.get("PORTAL_BAICHUAN_WRITE_USER_IDS", "").split(",")))
PORTAL_BAICHUAN_READ_ROLE_CODES = tuple(filter(None, os.environ.get("PORTAL_BAICHUAN_READ_ROLE_CODES", "").split(",")))
PORTAL_BAICHUAN_WRITE_ROLE_CODES = tuple(filter(None, os.environ.get("PORTAL_BAICHUAN_WRITE_ROLE_CODES", "").split(",")))
AGENT_PLATFORM_ENABLED = os.environ.get("PORTAL_AGENT_ENABLED") == "1"
AGENT_RUNTIME_URL = os.environ.get("PORTAL_AGENT_RUNTIME_URL", "")
AGENT_RUNTIME_SERVICE_TOKEN = os.environ.get("PORTAL_AGENT_RUNTIME_SERVICE_TOKEN", "")
AGENT_RUNTIME_ALLOWED_URLS = tuple(filter(None, os.environ.get("PORTAL_AGENT_RUNTIME_ALLOWED_URLS", "http://127.0.0.1:2024").split(",")))
AGENT_MAIN_GRAPH = os.environ.get("PORTAL_AGENT_MAIN_GRAPH", "main")
try:
    AGENT_RUNTIME_MODEL_PRESETS = json.loads(os.environ.get("PORTAL_AGENT_RUNTIME_MODEL_PRESETS", "{}"))
except (ValueError, TypeError):
    raise ImproperlyConfigured("Agent 模型预设必须为已授权模型的 JSON 对象。") from None
if not isinstance(AGENT_RUNTIME_MODEL_PRESETS, dict):
    raise ImproperlyConfigured("Agent 模型预设必须为已授权模型的 JSON 对象。")
try:
    AGENT_ROOT_POLICY = json.loads(os.environ.get("PORTAL_AGENT_ROOT_POLICY", '{"max_actions":2048,"max_model_calls":320,"max_tool_calls":1536,"max_launches":128,"max_concurrent":16,"max_active_ms":86400000,"deadline_seconds":172800}'))
except (ValueError, TypeError):
    raise ImproperlyConfigured("Agent 根运行保护必须为有限整数配置。") from None
if not isinstance(AGENT_ROOT_POLICY, dict) or any(type(AGENT_ROOT_POLICY.get(key)) is not int or not 1 <= AGENT_ROOT_POLICY[key] <= maximum for key, maximum in (("max_actions", 100000), ("max_model_calls", 10000), ("max_tool_calls", 100000), ("max_launches", 10000), ("max_concurrent", 64), ("max_active_ms", 604800000), ("deadline_seconds", 604800))):
    raise ImproperlyConfigured("Agent 根运行保护必须为有限整数配置。")
PRODUCT_MODEL_CALLS_ALLOWED = os.environ.get("PORTAL_PRODUCT_MODEL_CALLS_ALLOWED") == "1"
PRODUCT_FORMAL_RELEASE_ENABLED = os.environ.get("PORTAL_PRODUCT_FORMAL_RELEASE_ENABLED") == "1"
PRODUCT_REVIEWER_IDS = tuple(int(value) for value in os.environ.get("PORTAL_PRODUCT_REVIEWER_IDS", "").split(",") if value.isdigit())
PRODUCT_STORAGE_ROOT = Path(os.environ.get("PORTAL_PRODUCT_STORAGE_ROOT", BASE_DIR / ".runtime" / "product-private"))
TENDER_STORAGE_ROOT = Path(os.environ.get("PORTAL_TENDER_STORAGE_ROOT", BASE_DIR / ".runtime" / "tender-private"))
PORTAL_TENDER_INGESTION_ENABLED = os.environ.get("PORTAL_TENDER_INGESTION_ENABLED") == "1"
PORTAL_TENDER_MANUAL_REFRESH_ENABLED = os.environ.get("PORTAL_TENDER_MANUAL_REFRESH_ENABLED") == "1"
PORTAL_TENDER_SCHEDULE_ENABLED = os.environ.get("PORTAL_TENDER_SCHEDULE_ENABLED") == "1"
try:
    TENDER_LOOKBACK_DAYS = int(os.environ.get("PORTAL_TENDER_LOOKBACK_DAYS", "30"))
    TENDER_LEASE_SECONDS = int(os.environ.get("PORTAL_TENDER_LEASE_SECONDS", "180"))
    TENDER_HEARTBEAT_SECONDS = int(os.environ.get("PORTAL_TENDER_HEARTBEAT_SECONDS", "5"))
except ValueError:
    raise ImproperlyConfigured("Tender 时间配置必须为整数") from None
if not 1 <= TENDER_LOOKBACK_DAYS <= 30:
    raise ImproperlyConfigured("Tender 滚动窗口必须为 1 至 30 天")
if not 30 <= TENDER_LEASE_SECONDS <= 3600 or not 1 <= TENDER_HEARTBEAT_SECONDS <= 10:
    raise ImproperlyConfigured("Tender 租约必须为 30 至 3600 秒，心跳必须为 1 至 10 秒")
TENDER_RECOVERY_OPERATOR_IDS = tuple(int(value) for value in os.environ.get("PORTAL_TENDER_RECOVERY_OPERATOR_IDS", "").split(",") if value.isdigit())
PRODUCT_IMPORT_ROOTS = tuple(Path(value) for value in os.environ.get("PORTAL_PRODUCT_IMPORT_ROOTS", "").split(os.pathsep) if value)
PRODUCT_UPLOAD_MAX_BYTES = 20 * 1024 * 1024
PRODUCT_PARSER_PYTHON = Path(os.environ.get("PORTAL_PRODUCT_PARSER_PYTHON", BASE_DIR / ".runtime" / "product-parser-python" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")))
PRODUCT_PARSE_TIMEOUT_SECONDS = 120
PRODUCT_OCR_ENABLED = os.environ.get("PORTAL_PRODUCT_OCR_ENABLED", "1") == "1"
try:
    PRODUCT_MAX_ATTEMPTS = int(os.environ.get("PORTAL_PRODUCT_MAX_ATTEMPTS", "8"))
except ValueError:
    raise ImproperlyConfigured("产品任务执行次数上限必须为整数") from None
if not 1 <= PRODUCT_MAX_ATTEMPTS <= 32:
    raise ImproperlyConfigured("产品任务执行次数上限必须位于1至32之间")
PRODUCT_OUTPUT_PROFILE = "formal"
PRODUCT_BLUEPRINT_MAX_REVISIONS = 3
try:
    PRODUCT_LEASE_SECONDS = int(os.environ.get("PORTAL_PRODUCT_LEASE_SECONDS", "900"))
except ValueError:
    raise ImproperlyConfigured("产品任务租约必须为整数秒") from None
if not 180 <= PRODUCT_LEASE_SECONDS <= 3600:
    raise ImproperlyConfigured("产品任务租约必须位于180至3600秒之间")
try:
    PRODUCT_TECHNICAL_TARGET_CHARACTERS = int(os.environ.get("PORTAL_PRODUCT_TECHNICAL_TARGET_CHARACTERS", "50000"))
    PRODUCT_FEASIBILITY_TARGET_CHARACTERS = int(os.environ.get("PORTAL_PRODUCT_FEASIBILITY_TARGET_CHARACTERS", "70000"))
    PRODUCT_MAX_MODEL_CALLS = int(os.environ.get("PORTAL_PRODUCT_MAX_MODEL_CALLS", "256"))
except ValueError:
    raise ImproperlyConfigured("产品文档目标字数必须为整数") from None
if not (1000 <= PRODUCT_TECHNICAL_TARGET_CHARACTERS <= 300000
        and 1000 <= PRODUCT_FEASIBILITY_TARGET_CHARACTERS <= 300000):
    raise ImproperlyConfigured("产品文档目标字数必须位于1000至300000之间")
if PRODUCT_TECHNICAL_TARGET_CHARACTERS < 50000 or PRODUCT_FEASIBILITY_TARGET_CHARACTERS < 70000:
    raise ImproperlyConfigured("正式版技术方案不得少于50000字，可行性研究报告不得少于70000字")
if not 1 <= PRODUCT_MAX_MODEL_CALLS <= 1000:
    raise ImproperlyConfigured("产品模型调用上限必须位于1至1000之间")
PRODUCT_ENFORCE_OUTPUT_LENGTH = True
try:
    PRODUCT_WRITING_CONCURRENCY = int(os.environ.get("PORTAL_PRODUCT_WRITING_CONCURRENCY", "12"))
except ValueError:
    raise ImproperlyConfigured("产品章节写作并发数必须为整数") from None
if not 1 <= PRODUCT_WRITING_CONCURRENCY <= 32:
    raise ImproperlyConfigured("产品章节写作并发数必须位于1至32之间")
PRODUCT_STEP_MAX_ATTEMPTS = int(os.environ.get("PORTAL_PRODUCT_STEP_MAX_ATTEMPTS", "3"))
PRODUCT_STEP_RETRY_BASE_SECONDS = int(os.environ.get("PORTAL_PRODUCT_STEP_RETRY_BASE_SECONDS", "5"))
PRODUCT_STEP_RETRY_MAX_SECONDS = int(os.environ.get("PORTAL_PRODUCT_STEP_RETRY_MAX_SECONDS", "60"))
if not (1 <= PRODUCT_STEP_MAX_ATTEMPTS <= 5 and 1 <= PRODUCT_STEP_RETRY_BASE_SECONDS <= PRODUCT_STEP_RETRY_MAX_SECONDS <= 300):
    raise ImproperlyConfigured("产品步骤恢复参数超出允许范围")
PRODUCT_BLUEPRINT_ROUTE = os.environ.get("PORTAL_PRODUCT_BLUEPRINT_ROUTE", "product_blueprint")
PRODUCT_WRITING_ROUTE = os.environ.get("PORTAL_PRODUCT_WRITING_ROUTE", "product_writing")
PRODUCT_REVIEW_ROUTE = os.environ.get("PORTAL_PRODUCT_REVIEW_ROUTE", "product_review")
PRODUCT_DOCUMENT_PYTHON = Path(os.environ.get("PORTAL_PRODUCT_DOCUMENT_PYTHON", BASE_DIR / ".runtime" / "product-documents-python" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")))
PRODUCT_MERMAID_NODE = os.environ.get("PORTAL_MERMAID_NODE", "node")
PRODUCT_MERMAID_CHROMIUM = os.environ.get("PORTAL_MERMAID_CHROMIUM", "")
try:
    PRODUCT_DOCUMENT_RENDER_TIMEOUT_SECONDS = int(os.environ.get("PORTAL_PRODUCT_DOCUMENT_RENDER_TIMEOUT_SECONDS", "300"))
    PRODUCT_OFFICE_RENDER_TIMEOUT_SECONDS = int(os.environ.get("PORTAL_PRODUCT_OFFICE_RENDER_TIMEOUT_SECONDS", "300"))
except ValueError:
    raise ImproperlyConfigured("产品文档渲染超时必须为整数秒") from None
if not (30 <= PRODUCT_DOCUMENT_RENDER_TIMEOUT_SECONDS <= 1200
        and 30 <= PRODUCT_OFFICE_RENDER_TIMEOUT_SECONDS <= 1200):
    raise ImproperlyConfigured("产品文档渲染超时必须位于30至1200秒之间")


def _product_configuration(name):
    try:
        raw = os.environ.get(name, "{}")
        if len(raw) > 65536:
            raise ValueError
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (ValueError, TypeError):
        raise ImproperlyConfigured(f"{name} 必须为有效配置对象") from None


PRODUCT_TEMPLATE_APPROVAL = _product_configuration("PORTAL_PRODUCT_TEMPLATE_APPROVAL")
PRODUCT_OFFICE_RENDER_ENABLED = os.environ.get("PORTAL_PRODUCT_OFFICE_RENDER_ENABLED") == "1"
PRODUCT_OFFICE_RENDERER = os.environ.get("PORTAL_PRODUCT_OFFICE_RENDERER", "word")
if PRODUCT_OFFICE_RENDERER not in {"word", "libreoffice"}:
    raise ImproperlyConfigured("PORTAL_PRODUCT_OFFICE_RENDERER 必须为 word 或 libreoffice")
PRODUCT_LIBREOFFICE_EXECUTABLE = os.environ.get("PORTAL_PRODUCT_LIBREOFFICE_EXECUTABLE", "/usr/bin/libreoffice")
PRODUCT_UNO_PYTHON = os.environ.get("PORTAL_PRODUCT_UNO_PYTHON", "/usr/bin/python3")
PRODUCT_REVIEW_POLICY_REVISION = os.environ.get("PORTAL_PRODUCT_REVIEW_POLICY_REVISION", "")
PRODUCT_BLUEPRINT_KNOWLEDGE_MODE = os.environ.get(
    "PORTAL_PRODUCT_BLUEPRINT_KNOWLEDGE_MODE", "source_only_preview"
)
if PRODUCT_BLUEPRINT_KNOWLEDGE_MODE not in {"source_only_preview", "ragflow_required"}:
    raise ImproperlyConfigured(
        "PORTAL_PRODUCT_BLUEPRINT_KNOWLEDGE_MODE 必须为 source_only_preview 或 ragflow_required"
    )
PRODUCT_RETRIEVAL_ENABLED = os.environ.get("PORTAL_PRODUCT_RETRIEVAL_ENABLED") == "1"
PRODUCT_RETRIEVAL_URL = os.environ.get("PORTAL_PRODUCT_RETRIEVAL_URL", "")
PRODUCT_RETRIEVAL_ALLOWED_URLS = tuple(filter(None, os.environ.get("PORTAL_PRODUCT_RETRIEVAL_ALLOWED_URLS", "").split(",")))
PRODUCT_RETRIEVAL_TOKEN_ENV = os.environ.get("PORTAL_PRODUCT_RETRIEVAL_TOKEN_ENV", "")
PRODUCT_RETRIEVAL_AUTHORIZATIONS = _product_configuration("PORTAL_PRODUCT_RETRIEVAL_AUTHORIZATIONS")

# Native RAGFlow Q&A is independent of the blueprint's custom retrieval contract.
PRODUCT_KNOWLEDGE_ENABLED = os.environ.get("PORTAL_PRODUCT_KNOWLEDGE_ENABLED") == "1"
PRODUCT_KNOWLEDGE_AI_CALLS_ALLOWED = os.environ.get("PORTAL_PRODUCT_KNOWLEDGE_AI_CALLS_ALLOWED") == "1"
PRODUCT_KNOWLEDGE_LOCAL_HTTP = os.environ.get("PORTAL_PRODUCT_KNOWLEDGE_LOCAL_HTTP") == "1"
PRODUCT_KNOWLEDGE_URL = os.environ.get("PORTAL_PRODUCT_KNOWLEDGE_URL", "")
PRODUCT_KNOWLEDGE_ALLOWED_URLS = tuple(filter(None, os.environ.get("PORTAL_PRODUCT_KNOWLEDGE_ALLOWED_URLS", "").split(",")))
PRODUCT_KNOWLEDGE_TOKEN_ENV = os.environ.get("PORTAL_PRODUCT_KNOWLEDGE_TOKEN_ENV", "")
PRODUCT_KNOWLEDGE_MODEL_ROUTE = os.environ.get("PORTAL_PRODUCT_KNOWLEDGE_MODEL_ROUTE", "product_knowledge")
PRODUCT_KNOWLEDGE_AUTHORIZATIONS = _product_configuration("PORTAL_PRODUCT_KNOWLEDGE_AUTHORIZATIONS")
PRODUCT_KNOWLEDGE_AUTHORIZATION_REVISION = os.environ.get("PORTAL_PRODUCT_KNOWLEDGE_AUTHORIZATION_REVISION", "")
PRODUCT_WEB_SEARCH_ENABLED = os.environ.get("PORTAL_PRODUCT_WEB_SEARCH_ENABLED") == "1"
PRODUCT_WEB_SEARCH_PROVIDER = os.environ.get("PORTAL_PRODUCT_WEB_SEARCH_PROVIDER", "tavily")
PRODUCT_WEB_SEARCH_TOKEN_ENV = os.environ.get("PORTAL_PRODUCT_WEB_SEARCH_TOKEN_ENV", "")
PRODUCT_WEB_SEARCH_SEARXNG_URL = os.environ.get("PORTAL_PRODUCT_WEB_SEARCH_SEARXNG_URL", "")
PRODUCT_WEB_SEARCH_BING_RSS_ENABLED = os.environ.get("PORTAL_PRODUCT_WEB_SEARCH_BING_RSS_ENABLED") == "1"
PRODUCT_WEB_SEARCH_BING_RSS_SYSTEM_PROXY = os.environ.get("PORTAL_PRODUCT_WEB_SEARCH_BING_RSS_SYSTEM_PROXY") == "1"
HR_STORAGE_ROOT = Path(os.environ.get("PORTAL_HR_STORAGE_ROOT", BASE_DIR / ".runtime" / "hr-private"))

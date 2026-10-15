"""Business assistant entry; DeepSeek Harness owns the tool/model loop."""
from .product_assistant_runtime import LEASE_SECONDS, run, runtime_status
from . import product_web_search as web
from .product_service import ProductError


def web_status():
    try:
        web.configuration()
        return {"available": True, "code": "ready",
                "help": "开启后，可搜索本次问题中的公开检索词并读取相关网页；历史和企业资料不会发送给搜索服务。"}
    except ProductError as error:
        return {"available": False, "code": error.code,
                "help": "联网搜索未启用或服务配置无效，请联系管理员检查。"}

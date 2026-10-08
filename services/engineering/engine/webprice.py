# -*- coding: utf-8 -*-
"""互联网取价：百度检索（Crawl4AI + 本机 Edge）→ 百炼抽取 → 清洗 → 缓存。

设计要点：
  · 检索用百度（实测免费源里唯一稳定可抓的），页面用本机 Edge 渲染
  · 抽取用百炼（OpenAI 兼容接口），只回 JSON，不让模型算数
  · 同一个物料的结果写进 SQLite 缓存，默认 30 天内不再重复抓
  · 网价统一按『含税 ÷1.13 → 不含税』再乘品类系数，折算成工程批量价
"""
import asyncio
import datetime as dt
import json
import math
import os
import re
import sqlite3
import statistics
import urllib.parse
import urllib.request
import time
import threading

from engine.tiering import classify_tier, discount_for

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DB = os.path.join(ROOT, "data", "library", "网价缓存.sqlite")
TAX = 1.13


def read_dashscope_key():
    if os.environ.get("DISABLE_WEB_LOOKUP") == "1":
        return None
    key = os.environ.get("DASHSCOPE_API_KEY")
    if key:
        return key
    cfg = os.path.join(os.environ.get("APPDATA", ""), "see", "config.env")
    if os.path.exists(cfg):
        for line in open(cfg, encoding="utf-8"):
            m = re.match(r"\s*DASHSCOPE_API_KEY\s*=\s*(.+)", line)
            if m:
                return m.group(1).strip().strip('"').strip("'")
    return None


class Cache:
    def __init__(self, path=CACHE_DB):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.con = sqlite3.connect(path)
        self.con.execute("""CREATE TABLE IF NOT EXISTS webprice(
            key TEXT PRIMARY KEY, payload TEXT, created_at TEXT)""")
        self.con.commit()

    def get(self, key, days=30):
        # 分级保鲜期（借鉴同事技能包）：电缆/铜铝/钢材这类随行情跳动的 14 天，
        # 其余设备材料 90 天。到期视为无缓存 → 自动重查。
        name = str(key).split("|")[0]
        if re.search(r"电缆|铜芯|铝芯|铜排|铝排|镀锌钢|钢管|型钢|钢材|钢丝绳", name):
            days = min(days, 14)
        else:
            days = max(days, 90)
        row = self.con.execute("SELECT payload, created_at FROM webprice WHERE key=?",
                               (key,)).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row[0])
        except Exception:
            return None
        ttl = payload.get("_ttl_days") if isinstance(payload, dict) else None
        if ttl:
            days = min(days, float(ttl))
        if dt.datetime.fromisoformat(row[1]) < dt.datetime.now() - dt.timedelta(days=days):
            return None
        return payload

    def put(self, key, payload):
        self.con.execute("INSERT OR REPLACE INTO webprice(key, payload, created_at) VALUES(?,?,?)",
                         (key, json.dumps(payload, ensure_ascii=False),
                          dt.datetime.now().isoformat()))
        self.con.commit()

    def put_negative(self, key, payload, days=1):
        """取不到价也写缓存（默认 7 天），避免每次跑都重新抓一遍同样的空结果。"""
        payload = dict(payload or {})
        payload["_negative"] = True
        payload["_ttl_days"] = days          # 这类结果单独定保鲜期
        self.put(key, payload)

    def get_any(self, key, days=7):
        """读缓存（含失败结果），失败结果按较短有效期算。"""
        hit = self.get(key, days=days)
        return hit


def llm_base():
    return (os.environ.get("DASHSCOPE_BASE_URL")
            or "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/")


def llm_model():
    return os.environ.get("DASHSCOPE_MODEL") or "qwen-plus"


def ask_llm(prompt, key, model=None, timeout=60, max_tokens=None):
    model = model or llm_model()
    payload = {"model": model, "temperature": 0,
               "messages": [{"role": "user", "content": prompt}]}
    if max_tokens:
        payload["max_tokens"] = max_tokens
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        llm_base() + "/chat/completions",
        data=body, headers={"Authorization": "Bearer " + key,
                            "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    return d["choices"][0]["message"]["content"]


def parse_json(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


EXTRACT_PROMPT = """你是工程造价询价助手。下面是百度搜索结果的正文，请找出与
「{name}　{spec}」最接近的商品报价。

只输出 JSON，不要输出其它文字：
{{"found": true,
  "候选": [{{"型号": "", "单价": 数字, "单位": "", "含税": true,
            "平台": "天猫/淘宝/京东/1688/阿里巴巴/慧聪/品牌官网/行业站等，只填平台名",
            "标题": "该条报价的商品标题",
            "店铺": "店铺或供应商名称，没有就留空",
            "链接": "该条对应的网址，能从正文里认出来就填，认不出留空",
            "依据": "一句话"}}]}}

要求：
1. 单价只填数字，不带单位与货币符号；找不到就 found=false、候选为空数组。
2. 必须是同一设备/材料的价；配件、耗材、维保服务的价不要。
3. 最多 5 条候选，按与目标的相关度排序。
4. 平台、标题、链接要尽量填全，这是要写进报价单"数据来源"列的，不能编造。
5. 优先取电商平台（天猫、淘宝、京东、1688、阿里巴巴、慧聪）的商品单价；
   其次是行业站、品牌官网的报价单。招标/中标/竞争性磋商公告里的"项目总价、
   工程造价、投资额、预算金额"一律不能当单价，遇到这类页面直接忽略。
6. 如果正文里只有项目总价、没有商品单价，就 found=false，不要硬凑数字。

搜索结果正文：
{body}
"""


# ── 常驻浏览器会话 ──────────────────────────────────────────────────────
# ⚠ 以前是每搜一条就 `async with AsyncWebCrawler(...)`——等于每条检索都重新启一次
# Edge。实测一份 125 行的清单要发上百次检索，光"启动浏览器"就吃掉 200~400 秒，
# 这才是单份清单要 9 分钟的真凶（真正抓页面只占几十秒）。
# 现在整个进程共用一次浏览器会话：后台线程跑一个事件循环，所有检索都提交给它。
_CRAWL_LOOP = None
_CRAWL_THREAD = None
_CRAWLER = None
_CRAWL_LOCK = threading.Lock()
_CRAWL_SEM = None
CRAWL_CONCURRENCY = int(os.environ.get("CRAWL_CONCURRENCY", "4"))


def _browser_and_run_config(timeout):
    from crawl4ai import BrowserConfig, CrawlerRunConfig, CacheMode

    # 浏览器可配：本机 Windows 用 Edge（不额外下载），容器/服务器用镜像里的 Chromium
    channel = os.environ.get("CRAWL4AI_CHANNEL") or "msedge"
    in_docker = os.path.exists("/.dockerenv")
    if in_docker and not os.environ.get("CRAWL4AI_CHANNEL"):
        channel = "chromium"
    browser = BrowserConfig(browser_type="chromium", chrome_channel=channel, headless=True,
                            text_mode=True, viewport_width=1366, viewport_height=900,
                            user_agent_mode="random", verbose=False, ignore_https_errors=True,
                            extra_args=(["--no-sandbox", "--disable-dev-shm-usage"]
                                        if in_docker else None))
    run = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=timeout * 1000,
                           wait_until="domcontentloaded")
    return browser, run


async def _crawl_in_loop(urls, timeout):
    """在常驻事件循环里跑一批 URL：浏览器只启一次，之后一直复用。"""
    global _CRAWLER, _CRAWL_SEM
    from crawl4ai import AsyncWebCrawler
    if _CRAWL_SEM is None:
        _CRAWL_SEM = asyncio.Semaphore(CRAWL_CONCURRENCY)
    browser, run = _browser_and_run_config(timeout)
    if _CRAWLER is None:
        _CRAWLER = AsyncWebCrawler(config=browser)
        await _CRAWLER.start()
    out = []
    for u in urls:
        async with _CRAWL_SEM:
            try:
                res = await asyncio.wait_for(_CRAWLER.arun(url=u, config=run),
                                             timeout=timeout + 5)
                out.append({"url": u, "md": (res.markdown or "") if res.success else "",
                            "ok": bool(res.success),
                            "links": [l.get("href") for l in
                                      ((res.links or {}).get("external") or [])][:40]})
            except Exception:
                out.append({"url": u, "md": "", "ok": False, "links": []})
    return out


def _start_crawl_loop():
    global _CRAWL_LOOP, _CRAWL_THREAD
    _CRAWL_LOOP = asyncio.new_event_loop()

    def _runner():
        asyncio.set_event_loop(_CRAWL_LOOP)
        _CRAWL_LOOP.run_forever()

    _CRAWL_THREAD = threading.Thread(target=_runner, name="crawl4ai-loop", daemon=True)
    _CRAWL_THREAD.start()


def crawl(urls, timeout=25):
    """同步取页面：提交给常驻浏览器会话执行（线程安全）。"""
    global _CRAWLER
    if not urls:
        return []
    with _CRAWL_LOCK:
        if _CRAWL_LOOP is None or not _CRAWL_LOOP.is_running():
            _start_crawl_loop()
        loop = _CRAWL_LOOP
    try:
        fut = asyncio.run_coroutine_threadsafe(_crawl_in_loop(list(urls), timeout), loop)
        return fut.result(timeout=timeout * len(urls) + 120)
    except Exception:
        # 常驻会话挂了就丢掉重建，别把整批判死
        with _CRAWL_LOCK:
            _CRAWLER = None
        return [{"url": u, "md": "", "ok": False, "links": []} for u in urls]


def queries_for(name, spec, brand="", unit="", region=""):
    """检索式：按米计价的材料搜"每米多少钱"，其余搜整体价；第二条专门找附近厂子。"""
    # 规格必须进检索式：不带规格搜"PLC机柜 价格"和带规格搜"PLC机柜 600×800×1800 价格"
    # 是两个完全不同的结果。名称过长时优先保名称、但规格一定要留出位置。
    name_s = re.sub(r"\s+", " ", "%s %s" % (brand, name)).strip()
    spec_s = re.sub(r"\s+", " ", str(spec or "")).strip()
    spec_s = re.sub(r"^(规格|型号|技术参数|参数)[:：]\s*", "", spec_s)
    base = (name_s[:34] + " " + spec_s[:34]).strip() if spec_s else name_s[:60]
    short = name_s[:34]
    u = str(unit or "").strip().lower()
    if u in ("m", "米", "km", "千米", "m2", "m²", "平方米"):
        per = "每米价格" if u in ("m", "米", "km", "千米") else "每平方米价格"
        qs = ["%s %s" % (base, per)]
    else:
        qs = [base + " 价格"]
        if spec_s:
            # 第二条换成"名称+规格+厂家报价"，保证规格始终在检索式里
            qs.append("%s %s 厂家 报价" % (short, spec_s[:34]))
    # 第二条：优先找"附近的厂子"（本地供应商报价），而不是电商平台
    if region:
        qs.append("%s %s %s 厂家 报价" % (region, short, spec_s[:20]))
    qs.append("%s %s 淘宝 天猫 价格" % (short, spec_s[:16]) if spec_s
              else "%s 淘宝 天猫 价格" % short)
    return list(dict.fromkeys(qs))[:2]


def clean_price(cands, include_candidate=False):
    """多候选剔除离群值后，取**中低位**（约 40 分位）作为推荐价。

    用户口径是"检索性价比高的"：不挑最便宜的（怕低质/引流价），也不取中位数
    （容易被高端型号拉高），取中间偏下的那一档。
    """
    vals = []
    priced = []
    for c in cands or []:
        try:
            p = float(str(c.get("单价", "")).replace(",", "").replace("元", ""))
        except (TypeError, ValueError):
            continue
        if 1 <= p <= 5_000_000:
            vals.append(p)
            priced.append((p, c))
    if not vals:
        return None
    nums = sorted(vals)
    med = statistics.median(nums)
    keep = [v for v in nums if 0.25 * med <= v <= 4 * med] or nums
    keep = sorted(keep)
    if len(keep) <= 2:
        pick = keep[0]
    else:
        pick = keep[max(0, int(len(keep) * 0.4) - 1)]
    result = (pick, len(keep), nums[0], nums[-1])
    if include_candidate:
        return result + (next(c for p, c in priced if p == pick),)
    return result


PRICE_HINT = re.compile(r"(?:¥|￥)\s?\d{1,7}(?:\.\d{1,2})?|\d{1,7}(?:\.\d{1,2})?\s*元")

# 工程经验价格带：搜到的单价落在区间外，说明抓错了（零件价、单价单位不符、引流价）。
# 宁可弃用转暂估，也不能把"风机 5 元/台"这种数写进报价单。可在 settings.json 覆盖。
PRICE_BANDS = [
    # 先匹配更具体的（数组顺序即优先级）——系统集成类整包设备不能用单体件的区间
    # 柜体类放最前：叫"XX机柜/XX箱"的按柜体算，不能按里面的元器件算
    # 落地柜（机柜/开关柜/控制柜）与挂墙小箱（配电箱/控制箱）成本量级差很多，分开给区间
    # 网络机柜/19寸机柜是标准化产品，500~3000 元，不能用服务器机柜（几万）的价
    (["网络机柜", "19寸机柜", "19英寸机柜", "交换机机柜", "挂墙机柜"], 300, 8000),
    # 柜体必须按柜型分档：KYN 高压柜、MNS 低压柜、电容/滤波柜 量级差一倍以上，
    # 混进一条 1500~800000 的大区间里，区间中值 3.4 万会把普通低压柜估高一倍
    (["高压开关柜", "高压柜", "KYN", "GG1", "XGN", "环网柜"], 5000, 120000),
    (["低压配电柜", "低压柜", "MNS", "GGD", "GCK", "GCS", "XL-21", "配电屏"], 1500, 80000),
    (["电容补偿柜", "滤波柜", "补偿柜", "有源滤波"], 2000, 150000),
    (["机柜", "开关柜", "配电柜", "控制柜", "馈出柜", "补偿柜", "滤波柜", "联络柜",
      "进线柜", "电源柜", "屏柜", "柜体"], 1500, 800000),
    (["配电箱", "控制箱", "接线箱", "端子箱", "照明箱", "电源箱", "箱体", "防爆箱"], 300, 200000),
    (["监控分中心", "监控中心", "管理中心", "控制中心"], 50000, 3000000),
    (["交调站", "交通量调查"], 50000, 800000),
    (["称重", "计重", "动态衡"], 30000, 800000),
    # 注意顺序：线圈/天线这类"部件"必须排在"收费系统"整包前面，
    # 否则地感线圈（几十块一个）会被系统级的区间判成不合理
    (["线圈", "地感", "天线", "摄像机", "情报板", "指示灯", "控制箱"], 20, 30000),
    (["收费系统", "ETC门架", "收费机器人", "自助缴费", "称重检测"], 10000, 800000),
    (["分中心", "服务区监控"], 20000, 1500000),
    (["变压器"], 8000, 3000000),
    (["变频器", "软启动"], 2000, 800000),
    (["直流屏", "自动化", "保护装置", "后台"], 2000, 800000),
    # 桥架与母线槽量级差得远：100×100 的梯级桥架 20~40 元/m，
    # 1000A 封闭母线槽 1000~3000 元/m，混在一条区间里必然估偏
    (["母线", "母线槽"], 100, 20000),
    (["桥架", "梯级式", "托盘式", "槽式桥架", "槽盒", "金属线槽"], 10, 400),
    (["风机", "风扇"], 80, 60000),
    (["空调", "暖风机"], 800, 80000),
    (["灯具", "投光灯", "路灯", "照明"], 80, 30000),
    (["摄像机", "监控", "摄像头"], 200, 60000),
    (["交换机", "光端机", "收发器"], 100, 100000),
    (["水泵", "排污泵"], 500, 200000),
    (["仪表", "液位计", "料位计", "物位计", "变送器", "流量计", "密度计", "含量计",
      "传感器", "探测器", "分析仪", "监测仪"], 100, 300000),
    # 注意：钢丝绳/拉线是"按米称重"的材料，必须排在"拉绳开关"前面，
    # 否则 ∅4.5 的钢丝绳会被按开关价算成 300 元/m
    (["钢丝绳", "钢索", "拉线", "钢丝", "吊线"], 2, 800),
    # 网线/光纤是"按米"的材料，单价很低但用量大。不单列一条，落到
    # 「按计量单位×米」的兜底上会估成 20 元/m（网线实际 1.5~4 元/m）
    (["网线", "双绞线", "六类", "五类线", "超五类", "网络线"], 1.2, 12),
    (["光缆", "光纤", "尾纤", "跳线", "皮线"], 1.5, 30),
    (["断链", "跑偏", "拉绳", "撕裂", "打滑", "保护装置", "急停"], 200, 30000),
    # 通信管理机 / 网关 / 串口服务器：工业通信硬件，按"套=800"兜底太低
    (["管理机", "网关", "串口服务器", "协议转换"], 500, 50000),
    # 滑触线/接触轨是"按米"的导电轨，跟"充电系统套件"这种整包不是一回事：
    # 名字叫"系统套件"、计量单位是米时，绝不能拿系统级的区间中值去乘米数
    (["滑触线", "接触轨", "滑导线", "滑线"], 100, 2000),
    # 软件 / 系统集成 / 服务类：这类按「套=800」的实物辅材量级兜底会出笑话
    # （煤炭运销信息化管理系统估成 800 元）。必须放在 PLC/上位机之前，
    # 否则「上位机软件」会被 PLC 区间（200~200000）抢走。
    (["软件", "平台", "信息化", "管理系统", "算法", "小程序", "客户端",
      "定制开发"], 8000, 800000),
    (["控制系统", "装车控制", "集控", "调度系统"], 30000, 2000000),
    (["服务", "维保", "运维", "诊断", "技术服务"], 5000, 300000),
    # 工控机 / 采集仪 / 工作站 是"几千到几万"的整机，跟 PLC 模块（几百到几千）
    # 不是一个量级。混在 200~200000 里、区间中值 6324 会把 8000 的工控机估低，
    # 更会把本来按"台=800"兜底的采集仪估成 800 元（实际 5000~10000）。
    (["工控机", "工业计算机", "采集仪", "工作站", "一体机"], 2000, 80000),
    (["PLC", "模块", "触摸屏", "上位机"], 200, 200000),
]


def price_band(name):
    """返回该名称适用的 (下限, 上限)；没有匹配到品类就返回 None。"""
    t = str(name or "")
    for kws, lo, hi in PRICE_BANDS:
        if any(k in t for k in kws):
            return lo, hi
    return None


def band_guess(name, spec="", unit=""):
    """品类经验区间的代表取值（含规格尺寸调档）。

    ⚠ 以前一律取「下限 × 1.5」。交换机这类区间的下限（100 元）是家用小交换机的价，
    取 150 元就会把「工业级 16 口交换机」估成 150 元——用户一眼看出不合理。
    区间跨度大时改用几何中值（对数均匀分布的中位），并夹在
    [下限×1.5, 上限] 之间，再乘规格尺寸系数。

    返回 (取值, (下限, 上限), 尺寸说明)；没有匹配到品类时返回 (None, None, "")。
    """
    # 名称认不出品类时，把规格也带上再认一次：「高低压远程停送电审批流程」
    # 光看名字认不出是软件，规格里写着"定制开发"就认出来了
    band = price_band(name) or price_band("%s %s" % (name or "", spec or ""))
    if not band:
        return None, None, ""
    lo, hi = float(band[0]), float(band[1])
    if hi <= lo:
        hi = lo * 1.0001
    guess = math.sqrt(lo * hi)
    guess = min(max(guess, lo * 1.5), hi)
    f, fnote = size_factor(name, spec)
    tf, tnote = tray_factor(name, spec)
    if tf != 1.0:
        f, fnote = tf, tnote
    guess = min(hi, guess * f)
    # 按米计价的材料，单价再贵也就是母线槽那个量级。套用"系统/软件"这类
    # 整包区间（中值几万）再乘米数会直接算出几百万，必须夹住。
    if str(unit or "").strip().lower() in ("m", "米", "延米"):
        guess = min(guess, 5000.0)
    return round(guess, 2), (band[0], band[1]), fnote


DIM3 = re.compile(r"(\d{2,5})\s*[*×xX]\s*(\d{2,5})\s*[*×xX]\s*(\d{2,5})")
DIM2 = re.compile(r"(\d{2,5})\s*[*×xX]\s*(\d{2,5})")
AMP_RE = re.compile(r"(\d{2,5})\s*(?:A|安)(?![A-Za-z])")


def size_factor(name, spec):
    """按规格里的尺寸给一个档位系数：大柜子比小箱子贵，别一个价打天下。

    以 800×600×2000 的标准落地柜（0.96 m³）为 1.0 基准，等比折算并夹在 0.8~2.5。
    解析不到尺寸就返回 1.0。
    """
    # 先把"长/宽/高/深/厚"这类标注去掉，否则 600×宽800×高1800 这种写法解析不出来
    t = "%s %s" % (name or "", spec or "")
    t = re.sub(r"(?:mm|MM|Mm|毫米|cm|CM|厘米)", "", t)          # 去掉单位
    t = re.sub(r"（[^）]{0,3}）|\([^)]{0,3}\)", "", t)             # 去掉（高）（深）这类短标注
    t = re.sub(r"[长宽高深厚][:：]?", "", t)
    t = re.sub(r"[\s\u3000=＝:：]+", "", t)
    m = DIM3.search(t)
    if not m:
        return 1.0, ""
    a, b, c = sorted((float(m.group(1)), float(m.group(2)), float(m.group(3))))
    if not (50 <= a and c <= 5000):
        return 1.0, ""
    vol = (a / 1000.0) * (b / 1000.0) * (c / 1000.0)      # m³
    if vol <= 0:
        return 1.0, ""
    f = max(0.8, min(2.5, vol / 0.96))
    return round(f, 2), "按规格尺寸 %g×%g×%g mm（%.2f m³）折算档位系数 ×%.2f" % (a, b, c, vol, f)


def tray_factor(name, spec):
    """桥架 / 母线槽按规格调档：二维尺寸（宽×高）或额定电流。

    ⚠ 用户明确要求过「取价一定要带规格」。桥架以前只按品类区间给一个价，
    200×150 和 800×150 的桥架一个价、630A 和 2500A 的母线槽一个价，
    这种表拿出去没人信。

    桥架：以 200mm 宽为 1.0，按 (宽/200)^0.75 折算（钢重近似随宽度线性）。
    母线槽：以 1000A 为 1.0，按 (电流/1000)^0.4 折算。
    返回 (系数, 说明)；不适用返回 (1.0, "")。
    """
    t = "%s %s" % (name or "", spec or "")
    if not re.search(r"母线|桥架|槽盒|线槽", t):
        return 1.0, ""
    tt = re.sub(r"(?:mm|MM|Mm|毫米|cm|CM|厘米)", "", t)
    tt = re.sub(r"[\s\u3000=＝:：]+", "", tt)
    m = DIM2.search(tt)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        if 50 <= a and b <= 2000:
            w = max(a, b)                     # 桥架取"宽"
            f = max(0.5, min(4.0, (w / 200.0) ** 0.75))
            return round(f, 2), "按规格宽度 %gmm（%g×%g）折算档位系数 ×%.2f" % (w, a, b, f)
    m = AMP_RE.search(tt)
    if m:
        amp = float(m.group(1))
        if 32 <= amp <= 6300:
            f = max(0.6, min(4.0, (amp / 1000.0) ** 0.4))
            return round(f, 2), "按额定电流 %gA 折算档位系数 ×%.2f" % (amp, f)
    return 1.0, ""


# ── 真实性三道闸（借鉴同事技能包，2026-09-08 用户要求）──
FAKE_WORDS = re.compile(
    r"估算|内插|外推|保守|推算|中间档|取中值|区间中值|类比|大约|估计值|组价|"
    r"按整箱|降档|升档|相当于|近似|非标|控制价|拦标价|招标限价|招标控制")
SPEC_MISMATCH = re.compile(
    r"高于清单|低于清单|近似替代|可替代|同类产品|系列产品|仅供参考")
FAKE_SOURCE = re.compile(r"采购清单|产品说明|产品价目表|预算表|清单汇总")

# 「相关度闸」用的通用词：这些词在标题里出现不代表找到了同一个东西
GENERIC_TOKENS = {
    "系统", "设备", "装置", "材料", "配件", "价格", "报价", "安装", "工程",
    "产品", "厂家", "批发", "供应", "型号", "规格", "品牌", "采购", "定制",
}


def _cn_bigrams(s):
    """取中文字符串的所有 2 字组合，用于「名称 vs 页面标题」的相关度比对。"""
    cn = "".join(re.findall(r"[\u4e00-\u9fa5]+", str(s or "")))
    return {cn[i:i + 2] for i in range(len(cn) - 1)}


def reject_reason(name, spec, price, src, note, link=""):
    """真实性三道闸：返回拒绝原因；None 表示这条报价可信可用。

    ① 备注/来源含推算字样（估算/外推/类比/中值/限价…）→ 不是实价
    ② 规格口径自曝不符（近似替代/仅供参考…）
    ③ 取价与其来源挂牌价偏差 > 15% → 自相矛盾
    另：来源文件是"采购清单/产品说明"类的当场拒（那类文件不可能有成交价）
    """
    blob = "%s %s %s" % (src or "", note or "", name or "")
    if FAKE_WORDS.search(blob):
        return "含推算字样（估算/外推/类比/中值/限价），不是实价"
    if SPEC_MISMATCH.search(blob):
        return "备注自曝与清单规格不符"
    if FAKE_SOURCE.search(str(src or "")):
        return "来源是采购清单/产品说明类文件，不可能有成交价（伪成交）"
    try:
        p = float(price or 0)
    except (TypeError, ValueError):
        return "价格不是数字"
    if p <= 0:
        return "价格为 0"
    # ④ 相关度闸：抓到的页面标题必须和清单项有共同关键词。
    #    没有这道闸，会出现「工业以太网模拟信号隔离器 17.3 元」这种页面被挂到
    #    「通讯接口（通讯OPC，与控制器匹配）」头上——比标 0 元更坏：看着像真价。
    if note:
        # 只拿标题做比对，且标题得有实质内容——有的抽取只回「百度爱采购」
        # 这种平台名，那属于"没抓到标题"，不能据此判抓错
        bt = _cn_bigrams(note) - GENERIC_TOKENS
        nt = _cn_bigrams(name) - GENERIC_TOKENS
        if len(nt) >= 2 and len(bt) >= 2 and not (nt & bt):
            return ("抓到的页面「%s」与清单项「%s」无共同关键词，判为抓错页面"
                    % (str(note)[:24], str(name)[:16]))
    band = price_band(name)
    # 搜索到的是**真实挂牌价**，只在"明显不可能是这个东西"时才拒：
    # 下限放到 0.3 倍——360 元的照明配电箱、888 元的防爆机柜都是真实存在的低价型号；
    # 但 5 元的风机、30 元的机柜仍然会被拦掉。
    if band and not (band[0] * 0.3 <= p <= band[1] * 3):
        return "取价 %.0f 元严重偏离「%s」的合理区间（%.0f~%.0f）" % (
            p, str(name)[:12], band[0], band[1])
    m = re.search(r"[¥￥]\s?(\d{1,7}(?:\.\d{1,2})?)|(\d{1,7}(?:\.\d{1,2})?)\s*元", blob)
    if m:
        quoted = float(m.group(1) or m.group(2))
        if quoted > 1 and abs(quoted - p) / max(quoted, 1) > 0.15:
            return "取价 %.0f 与来源挂牌价 %.0f 偏差超 15%%" % (p, quoted)
    return None


ESTIMATE_PROMPT = """你是工程造价询价专家。请给出下面这个设备/材料在**国内工程市场**的参考单价。

名称：{name}
规格/型号：{spec}
计量单位：{unit}
采购数量：{qty}
项目所在地区：{region}

只输出 JSON，不要输出其它文字：
{{"找到": true, "低位": 数字, "中位": 数字, "高位": 数字,
  "依据": "一句话说明这个价怎么来的：市场常见价 / 按铜价折算 / 按规格类推 / 按同品类类推"}}

要求：
1. 数字为该「{unit}」的单价，单位元，只填数字。
2. 给区间，不要给假精确的单点；数量大要考虑批量折扣。
3. 实在无法判断就把区间放宽，并在依据里写清是"粗估"。
4. 不要拒绝回答，工程询价本来就是按经验给区间的。
"""


def estimate_by_llm(name, spec, unit, qty, cfg, key, cache):
    """联网彻底取不到价时的最后一道：让大模型按经验给区间（明确标注是估值）。

    这是"给个能用的数"和"给 0 元"之间的区别——用户口径：宁可给标注清楚的
    经验估值，也不要一个 0 元把总价拉垮。
    """
    ckey = "llmest|" + "|".join([re.sub(r"\s+", "", name), str(spec or "")[:40], unit or ""])
    hit = cache.get(ckey, days=7)
    if hit:
        return hit
    region = str(cfg.get("project_region") or "陕西")
    try:
        raw = ask_llm(ESTIMATE_PROMPT.format(name=name, spec=spec, unit=unit,
                                             qty=qty, region=region), key, timeout=45)
        got = parse_json(raw) or {}
    except Exception as e:  # noqa: BLE001
        return {"found": False, "备注": "经验估值也失败: %s" % str(e)[:60]}
    try:
        lo = float(str(got.get("低位")).replace(",", "").replace("元", ""))
        mid = float(str(got.get("中位")).replace(",", "").replace("元", ""))
        hi = float(str(got.get("高位")).replace(",", "").replace("元", ""))
    except (TypeError, ValueError):
        return {"found": False, "备注": "经验估值没解析出数字"}
    if not (0 < lo <= mid <= hi < 1e9):
        return {"found": False, "备注": "经验估值区间不合理"}
    band = price_band(name)
    if band and not (band[0] * 0.3 <= mid <= band[1] * 3):
        return {"found": False,
                "备注": "经验估值 %.0f 元严重偏离「%s」的合理区间，不采用" % (mid, name[:12])}
    res = {"found": True, "工程价": round(mid, 2),
           "原始网价（含税）": round(mid, 2), "不含税": round(mid / 1.13, 2),
           "品类": "AI经验估值", "系数": 1.0, "系数说明": "未取到网价，按经验区间取值",
           "价格区间": [lo, hi], "候选数": 1,
           "平台": "AI经验估值（非网价）", "标题": "%s 经验区间 %.0f~%.0f 元/%s"
           % (name, lo, hi, unit),
           "来源": "AI经验估值", "链接": "",
           "依据": str(got.get("依据") or "")[:120],
           "抓取日期": dt.date.today().isoformat(),
           "备注": "⚠ 本条未在电商/行业站取到真实报价，是按大模型工程经验给的估值，必须询价复核"}
    cache.put(ckey, res)
    return res


def snippets(md, window=600, max_parts=8, max_chars=9000):
    """搜索页前面大半是导航，这里按『出现价格的位置』切片，喂给模型更准也更省。"""
    spans = []
    for m in PRICE_HINT.finditer(md or ""):
        a, b = max(0, m.start() - window), min(len(md), m.end() + window)
        if spans and a <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], b))
        else:
            spans.append((a, b))
        if len(spans) >= max_parts:
            break
    if not spans:
        mid = len(md) // 3
        return (md or "")[mid:mid + max_chars]
    out, total = [], 0
    for a, b in spans:
        piece = md[a:b]
        if total + len(piece) > max_chars:
            piece = piece[:max(0, max_chars - total)]
        out.append(piece)
        total += len(piece)
        if total >= max_chars:
            break
    return "\n---\n".join(out)


SEARCH_ENGINES = (
    ("百度", "https://www.baidu.com/s?wd=%s"),
    ("搜狗", "https://www.sogou.com/web?query=%s"),
)
MIN_PAGE = 1200       # 正文短于这个长度基本就是风控空壳页
_RATE_LOCK = threading.Lock()
_RATE_NEXT = [0.0]
_BLOCK_STREAK = [0]       # 连续多少次搜出来是空壳页——用来判断是不是被风控了
_BLOCK_GIVEUP = [0]       # 本次测算里已经"退避重试"过几次；源被限流就干脆停手
_DEADLINE = [0.0]         # 联网取价的全局截止时间戳，到点立刻停手
_SESSION_MEMO = {}        # 本次进程内已搜过的结果（含失败）——同一次测算里
                          # 库+网 与 纯网 两条线会搜同一批物料，不重复搜
_SESSION_LOCK = threading.Lock()


def session_get(key):
    with _SESSION_LOCK:
        return _SESSION_MEMO.get(key)


def session_put(key, val):
    with _SESSION_LOCK:
        _SESSION_MEMO[key] = val


def set_deadline(seconds):
    _DEADLINE[0] = time.time() + float(seconds) if seconds else 0.0
    _BLOCK_GIVEUP[0] = 0          # 每次测算重新计数


def past_deadline():
    return bool(_DEADLINE[0]) and time.time() >= _DEADLINE[0]


def _deadline_left():
    return (_DEADLINE[0] - time.time()) if _DEADLINE[0] else 1e9


def throttle(gap=None, slots=1):
    """全局节流：多线程并发取价时，保证对外请求不要挤在一起被搜成风控。"""
    # 节流 2.5 秒：实测同一批清单里，快节奏搜到第 6~8 条就会被百度/搜狗限流，
    # 后面全部返回空壳页。宁可慢一点，也要把真实价取到。
    g = float(gap if gap is not None else os.environ.get("WEB_THROTTLE", "2.5"))
    with _RATE_LOCK:
        now = time.time()
        wait = max(0.0, _RATE_NEXT[0] - now)
        _RATE_NEXT[0] = max(now, _RATE_NEXT[0]) + g * max(1, int(slots))
    if wait > 0:
        time.sleep(wait)


def crawl_search(q, timeout=20):
    """搜一个关键词：**百度与搜狗并行抓**，谁有可用正文就用谁。

    以前是"百度失败再试搜狗"串行，一条要等两次；现在并行，风控时省一半时间。
    """
    # 源已经被限流到搜不出东西了就别再死磕：一次测算里退避重试超过 3 次
    # 就直接停手（结果一样是搜不到，但省下每份清单 2~3 分钟的无效等待）
    if past_deadline() or _BLOCK_GIVEUP[0] >= 3:
        return []
    urls = [(nm, tpl % urllib.parse.quote(q)) for nm, tpl in SEARCH_ENGINES]
    throttle(slots=len(urls))
    try:
        pages = crawl([u for _, u in urls], timeout=timeout)
    except Exception:
        pages = []
    good = []
    for (nm, _u), p in zip(urls, pages):
        if p.get("ok") and len(p.get("md") or "") >= MIN_PAGE:
            p["引擎"] = nm
            good.append(p)
    if good:
        _BLOCK_STREAK[0] = 0
        return good
    # 所有引擎都返回空壳页：大概率是被限流了，退避一会儿再试一次
    _BLOCK_STREAK[0] += 1
    if _BLOCK_STREAK[0] >= 4:
        left = _deadline_left()
        if left <= 5:
            return []
        # ⚠ 原来这里退避 80~90 秒且不检查时间预算，一份清单光"等风控过去"
        # 就要耗掉两份钟，而实测退避完照样是被限流的空壳页。
        wait = max(0.0, min(30.0, 20.0 * _BLOCK_STREAK[0], left))
        time.sleep(wait)
        _BLOCK_STREAK[0] = 0
        _BLOCK_GIVEUP[0] += 1
        throttle(slots=len(urls))
        try:
            pages = crawl([u for _, u in urls], timeout=timeout)
        except Exception:
            return []
        for (nm, _u), p in zip(urls, pages):
            if p.get("ok") and len(p.get("md") or "") >= MIN_PAGE:
                p["引擎"] = nm
                good.append(p)
    return good


def cache_key(name, spec, unit=""):
    """网价缓存的键：名称 + 规格 + 单位（去空白）。"""
    return "|".join([re.sub(r"\s+", "", str(name or "")),
                     re.sub(r"\s+", "", str(spec or ""))[:40],
                     str(unit or "")])


def price_item(name, spec, unit, qty, cfg, key, cache, brand="", attempt=1):
    """单个物料的网价（含缓存）。

    attempt=1 标准检索式；attempt=2 简化名称 + 厂家；attempt=3 只用核心词 + 换引擎。
    失败不缓存、交给上层重试——"抽取超时"这类偶发失败不能一次就判死。
    """
    ckey = cache_key(name, spec, unit)
    if attempt == 1:
        hit = cache.get(ckey) or cache.get_any(ckey)
        if hit:
            hit["缓存"] = True
            return hit
        # 同一次测算里已经搜过这个物料（含搜不到）就直接复用，别搜第二遍
        memo = session_get(ckey)
        if memo is not None:
            return dict(memo, 本次复用=True)

    pages = []
    region = str(cfg.get("project_region") or "")
    if attempt == 1:
        qs = queries_for(name, spec, brand, unit, region)
    elif attempt == 2:
        # 换词再搜：去掉型号规格，只留核心名称 + 厂家报价
        core = re.sub(r"[（(].*?[)）]", "", name).strip()
        qs = ["%s 厂家 报价" % core, "%s %s 价格 报价" % (region, core[:30])]
    else:
        # 第三轮：把型号也带上，换另一套词，避开前两轮踩过的坑
        core = re.sub(r"[（(].*?[)）]", "", name).strip()
        qs = ["%s 多少钱 一台" % core, "%s %s 现货 价格" % (spec[:24], core[:20])]
    # 逐条检索式「抓到就抽、抽到就停」——原来是把两条检索式的页面都抓完再抽一次，
    # 第一条命中时第二条纯属白跑，这正好是一半的耗时。
    med = n = lo = hi = None
    best = {}
    pages, got = [], {}
    last_err = "未找到有效价格"
    for q in qs:
        if past_deadline():
            last_err = "超出本次联网取价时间预算"
            break
        pages = crawl_search(q, timeout=25)
        if not pages:
            last_err = "检索页抓取失败（疑似被风控）"
            continue
        body = snippets("\n\n".join(p["md"] for p in pages if p["ok"]))
        if not body.strip():
            last_err = "检索页无正文"
            continue
        try:
            raw = ask_llm(EXTRACT_PROMPT.format(name=name, spec=spec, body=body), key,
                          timeout=120)      # 正文长时 60 秒会超时，给到 120
            got = parse_json(raw) or {"found": False}
        except Exception as e:  # noqa: BLE001
            last_err = "抽取失败: %s" % str(e)[:80]
            continue
        cleaned = clean_price(got.get("候选"), include_candidate=True)
        if not cleaned:
            last_err = "未找到有效价格"
            continue
        med, n, lo, hi, best = cleaned
        break
    if med is None:
        res = {"found": False, "备注": last_err, "_retryable": True}
        if attempt == 1:
            session_put(ckey, res)
            # 失败也要落缓存，但只落 12 小时：
            # ⚠ 以前失败一律不缓存，导致同一批 44 份清单每跑一遍都要把
            # 取不到价的条目重新搜一轮——整批重跑一点不快，白白多花 2 小时。
            # "超出时间预算"不算真失败（只是没轮到），不缓存，下次还能搜。
            if "时间预算" not in last_err:
                try:
                    cache.put_negative(ckey, res, days=0.5)
                except Exception:  # noqa: BLE001
                    pass
        return res

    band = price_band(name)
    if band and not (band[0] * 0.3 <= med <= band[1] * 3):
        res = {"found": False,
               "备注": ("搜到的价 %.2f 元/单位 不在「%s」的工程合理区间 %.0f~%.0f 内，"
                        "判定为抓错（零件价/引流价），已弃用" % (med, name[:14], band[0], band[1])),
               "_out_of_band": True}
        # 价格带拒绝：只缓存 6 小时——同一批 44 份清单里同样的物料不重复搜，
        # 但规则调整后第二天就会重新搜（不写缓存会把整批拖慢一倍）
        cache.put_negative(ckey, res, days=0.25)
        return res
    tier = classify_tier(cfg.get("online_discount", {}), name, "", "")
    coef, why = discount_for(tier, qty, cfg.get("online_discount", {}))
    low_warn = ""
    if band and med <= band[0] * 1.2:
        low_warn = ("⚠ 取到的是该品类的低位价（合理区间 %.0f~%.0f），有可能是空柜/不含"
                    "元器件的价，务必复核；" % (band[0], band[1]))
    ex_tax = med / TAX
    final = ex_tax * coef if coef else None
    # 来源要能写进报价单：平台 + 商品标题 + 链接 + 抓取日期
    cands = got.get("候选") or []
    plat = str(best.get("平台") or best.get("来源") or "").strip()[:20]
    title = str(best.get("标题") or "").strip()[:70]
    shop = str(best.get("店铺") or "").strip()[:30]
    link = str(best.get("链接") or "").strip()[:200]
    src = "｜".join(x for x in (plat, shop, title) if x) or "百度网页"
    urls = [p["url"] for p in pages if p.get("ok")][:2]
    detail = [{"平台": str(c.get("平台") or c.get("来源") or "").strip()[:20],
               "店铺": str(c.get("店铺") or "").strip()[:30],
               "标题": str(c.get("标题") or "").strip()[:70],
               "链接": str(c.get("链接") or "").strip()[:200],
               "单价": c.get("单价"), "单位": c.get("单位"), "依据": c.get("依据")}
              for c in cands[:5]]
    res = {"found": bool(final),
           "原始网价（含税）": round(med, 2),
           "不含税": round(ex_tax, 2),
           "品类": tier, "系数": coef, "系数说明": why,
           "工程价": round(final, 2) if final else None,
           "候选数": n, "价格区间": [lo, hi],
           "来源": src, "平台": plat, "标题": title, "店铺": shop, "链接": link,
           "候选明细": detail, "检索页": urls,
           "备注": "" if coef else why,
           "预警": low_warn,
           "抓取日期": dt.date.today().isoformat()}
    cache.put(ckey, res)
    session_put(ckey, res)
    return res


MEMO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "library", "网价入库.jsonl")


def remember(name, spec, unit, price, meta):
    """把联网查到的价回写进知识库，下次测算直接命中历史价库（省掉几分钟检索）。"""
    if not price:
        return
    band = price_band(name)
    if band and not (band[0] <= float(price) <= band[1]):
        return          # 明显不合理的价不许进库，否则会一直污染后续测算
    rec = {"来源文件": "互联网检索自动入库｜%s" % (meta.get("平台") or "网络"),
           "表名": "网价", "行号": "", "类别": "设备/材料",
           "名称": name, "品牌": meta.get("店铺") or "", "型号": "",
           "规格": spec or "", "单位": unit or "", "数量": None,
           "单价元": price, "金额元": None,
           "备注": (meta.get("标题") or "")[:120],
           "出现次数": 1, "入库时间": meta.get("抓取日期") or dt.date.today().isoformat(),
           "链接": meta.get("链接") or ""}
    try:
        os.makedirs(os.path.dirname(MEMO), exist_ok=True)
        with open(MEMO, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def load_memo():
    """读回自动入库的网价。"""
    out = []
    if not os.path.exists(MEMO):
        return out
    try:
        for line in open(MEMO, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            try:
                p = float(rec.get("单价元") or 0)
            except Exception:
                continue
            band = price_band(rec.get("名称"))
            if p and (not band or band[0] <= p <= band[1]):
                out.append(rec)
    except Exception:
        pass
    return out


LABOR_RATE_PROMPT = """下面是一批网页正文，请找出「{region}」建筑安装工程的人工工日单价
（元/工日，也叫综合工日单价、人工单价、日工资）。

只输出 JSON：
{{"found": true, "工日单价": 数字, "区间": [低, 高], "年度": "", "来源": "", "依据": "一句话"}}

要求：
1. 只填数字，不带单位；查不到就 found=false。
2. 优先取政府发布的计价依据（住建厅、造价站、信息价文件），其次取市场行情。
3. 区间填原文给的区间；没有区间就填 [单价, 单价]。

网页正文：
{body}
"""


def labor_day_rate(region, cfg, key, cache, ttl_days=30):
    """联网查当地人工工日单价（元/工日）。查不到就返回 found=False。"""
    ckey = "LABORRATE|" + (region or "陕西")
    hit = cache.get(ckey, days=ttl_days)
    if hit:
        hit["缓存"] = True
        return hit

    region = region or "陕西"
    queries = [
        "%s 建设工程 人工工日单价 元/工日 造价" % region,
        "%s 建筑安装工程 综合工日单价 调整 文件" % region,
    ]
    pages = []
    for q in queries:
        pages.extend(crawl(["https://www.baidu.com/s?wd=" + urllib.parse.quote(q)],
                           timeout=20))
    # 顺着结果打开 3 个看着像正文的页面再抽一次，比只看搜索摘要准
    links = []
    for p in pages:
        for href in p.get("links") or []:
            if str(href).startswith("http") and not any(
                    x in href for x in ("baidu.com", "bcebos", "javascript")):
                links.append(href)
    links = list(dict.fromkeys(links))[:1]
    if links:
        pages.extend(crawl(links, timeout=20))

    body = snippets("\n\n".join(p["md"] for p in pages if p["ok"]),
                    max_parts=10, max_chars=11000)
    if not body.strip():
        return {"found": False, "备注": "检索页抓取失败"}
    try:
        got = parse_json(ask_llm(LABOR_RATE_PROMPT.format(region=region, body=body), key)) or {}
    except Exception as e:  # noqa: BLE001
        return {"found": False, "备注": "抽取失败: %s" % str(e)[:80]}

    try:
        rate = float(str(got.get("工日单价")).replace(",", "").replace("元", ""))
    except (TypeError, ValueError):
        return {"found": False, "备注": "未抽到工日单价"}
    if not (30 <= rate <= 2000):
        return {"found": False, "备注": "工日单价异常：%s" % rate}
    rng = got.get("区间") or [rate, rate]
    try:
        rng = [float(str(x)) for x in rng]
    except (TypeError, ValueError):
        rng = [rate, rate]
    res = {"found": True, "工日单价": round(rate, 2),
           "区间": [min(rng), max(rng)], "年度": str(got.get("年度") or ""),
           "来源": str(got.get("来源") or "")[:80],
           "依据": str(got.get("依据") or "")[:120],
           "抓取日期": dt.date.today().isoformat()}
    cache.put(ckey, res)
    return res


LABOR_PROMPT = """你是劳务分包询价助手。下面是百度搜索结果的正文，请找出
「{name}」在当地（{region}）的劳务分包综合单价。

只输出 JSON：
{{"found": true,
  "候选": [{{"项目": "", "单价": 数字, "单位": "", "来源": "", "依据": "一句话"}}]}}

要求：
1. 只要包工（劳务施工）的价，含设备材料或含主材的价不要。
2. 单价只填数字；找不到就 found=false、候选为空数组。
3. 最多 5 条候选，按相关度排序，并优先取区间偏上的价。

搜索结果正文：
{body}
"""


def price_labor_item(name, unit, region, cfg, key, cache, spec=""):
    """劳务分包单价的联网取价（不压价，取区间偏上）。"""
    ckey = "LABOR|" + "|".join([re.sub(r"\s+", "", name), unit or "", region or ""])
    hit = cache.get(ckey)
    if hit:
        hit["缓存"] = True
        return hit

    qs = ["%s 劳务 单价 元/%s" % (name, unit or "单位"),
          "%s 安装 人工费 %s" % (name, region or "陕西")]
    pages = []
    for q in qs[:2]:
        pages.extend(crawl(["https://www.baidu.com/s?wd=" + urllib.parse.quote(q)],
                           timeout=20))
    body = snippets("\n\n".join(p["md"] for p in pages if p["ok"]))
    if not body.strip():
        return {"found": False, "备注": "检索页抓取失败"}
    try:
        got = parse_json(ask_llm(LABOR_PROMPT.format(name=name, region=region or "陕西",
                                                     body=body), key)) or {}
    except Exception as e:  # noqa: BLE001
        return {"found": False, "备注": "抽取失败: %s" % str(e)[:80]}
    cleaned = clean_price(got.get("候选"))
    if not cleaned:
        return {"found": False, "备注": "未找到劳务价"}
    _, n, lo, hi = cleaned
    # 不压价：取区间偏上（75% 分位），再乘地区系数
    vals = sorted(float(str(c.get("单价", "0")).replace(",", "")) for c in got.get("候选")
                  if str(c.get("单价", "")).replace(".", "").isdigit())
    vals = [v for v in vals if 1 <= v <= 5_000_000] or [lo, hi]
    pos = vals[int((len(vals) - 1) * 0.75)]
    rf = cfg.get("labor", {}).get("region_factor", {}).get(region or "", 1.0)
    final = pos * rf
    src = next((str(c.get("来源"))[:60] for c in got.get("候选") or [] if c.get("来源")), "")
    res = {"found": True, "劳务网价": round(pos, 2), "地区系数": rf,
           "劳务单价": round(final, 2), "候选数": n, "价格区间": [lo, hi],
           "来源": src, "抓取日期": dt.date.today().isoformat()}
    cache.put(ckey, res)
    return res


def price_one_in_thread(args):
    """线程安全的单条取价（每条用独立 sqlite 连接）。"""
    name, spec, unit, qty, cfg, key, attempt = args
    try:
        return name, price_item(name, spec, unit, qty, cfg, key, Cache(), attempt=attempt)
    except Exception as e:  # noqa: BLE001
        return name, {"found": False, "备注": "取价异常: %s" % str(e)[:60],
                      "_retryable": True}


def price_many_parallel(tasks, cfg, workers=4, budget_sec=None):
    """并行取价 + 失败自动重搜。

    串行时每条要 10~25 秒，并行后整批时间约等于最慢的那一条。
    第一轮用标准检索式；没取到的**换词再搜两轮**（去掉型号只留核心名、换引擎、
    加"厂家/多少钱/现货"）。三轮都拿不到才算真没价，交给上层做暂估。
    """
    from concurrent.futures import ThreadPoolExecutor

    key = read_dashscope_key()
    if not key or not tasks:
        return {}
    budget = float(budget_sec if budget_sec is not None
                   else os.environ.get("WEB_BUDGET_SEC", "240"))
    set_deadline(budget)      # 硬截止：单条也别想拖垮整批
    t_start = time.time()
    out = {}
    todo = list(tasks)
    for attempt in (1, 2, 3):
        if not todo:
            break
        if attempt > 2:
            break             # 默认最多两轮换词重搜，第三轮留给经验估值
        # 时间预算：整批联网取价必须在预算内跑完，否则后面会拖垮工作流（Dify 会 504）。
        # 超预算的条目直接留给上层做经验估值，别再死磕搜索。
        left = budget - (time.time() - t_start)
        if left <= 15:
            for (n, s, u, q) in todo:
                out.setdefault(n, {"found": False,
                                   "备注": "超出本次联网取价时间预算，转经验估值"})
            break
        args = [(n, s, u, q, cfg, key, attempt) for (n, s, u, q) in todo]
        round_out = {}
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            for name, res in ex.map(price_one_in_thread, args):
                round_out[name] = res
        still = []
        for (n, s, u, q) in todo:
            r = round_out.get(n) or {}
            if r.get("found"):
                r["检索轮次"] = attempt
                out[n] = r
            else:
                still.append((n, s, u, q))
                out[n] = r
        if still and attempt < 3:
            # 还有预算才继续换词重搜；预算不够就交给经验估值
            if budget - (time.time() - t_start) <= 20:
                for (n, s, u, q) in still:
                    out[n] = {"found": False,
                              "备注": "超出本次联网取价时间预算，转经验估值"}
                break
            time.sleep(4)      # 换词前歇一下，别踩着风控的节奏继续打
        todo = still
    for n in out:
        out[n].setdefault("检索轮次", 1)
    return out


def price_items(items, cfg, limit=None):
    """批量取价：返回 {名称: 结果}。"""
    key = read_dashscope_key()
    if not key:
        return {}
    cache = Cache()
    out = {}
    for x in (items[:limit] if limit else items):
        name = x.get("项目名称") or x.get("名称") or ""
        spec = x.get("备注") or x.get("规格") or ""
        out[name] = price_item(name, spec, x.get("单位") or "", x.get("数量") or 0,
                               cfg, key, cache)
    return out


def _self_check():
    disabled = os.environ.get("DISABLE_WEB_LOOKUP")
    os.environ["DISABLE_WEB_LOOKUP"] = "1"
    try:
        assert read_dashscope_key() is None
    finally:
        if disabled is None:
            os.environ.pop("DISABLE_WEB_LOOKUP", None)
        else:
            os.environ["DISABLE_WEB_LOOKUP"] = disabled

    cands = [
        {"单价": "300元", "平台": "首项"},
        {"单价": "100", "平台": "选中项"},
        {"单价": 200, "平台": "中间项"},
        {"单价": 10000, "平台": "离群项"},
    ]
    plain = clean_price(cands)
    linked = clean_price(cands, include_candidate=True)
    assert plain == linked[:4] == (100.0, 3, 100.0, 10000.0)
    assert linked[4] is cands[1]


if __name__ == "__main__":
    _self_check()
    print("webprice self-check passed")

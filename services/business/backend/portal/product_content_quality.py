"""Explainable fact-boundary checks, independent of Django and model access.

This guard detects high-signal issues, not arbitrary factual truth. Callers must
pass *trusted project evidence* separately from public technical references and
retain independent full-text review. A successful check is not publication or
human-review approval. Neither evidence nor authored content is rewritten here.
"""

from collections import Counter
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
import hashlib
from pathlib import Path
import re
from typing import Any


_CN = "零〇一二两三四五六七八九十百千万亿点"
_NUM = rf"(?:\d+(?:\.\d+)?|(?<!统)[{_CN}]+)"
_UNITS = (
    "毫秒|秒钟|秒|分钟|小时|工作日|天|日|星期|周|个月|月|季度|年|"
    "亿元|万元|元|人民币|台|套|节点|条|项|次|个|人|字节|"
    "TB|GB|MB|KB|TiB|GiB|MiB|KiB|Mbps|Gbps|QPS|TPS|%|％"
)
_QUANTITY = re.compile(rf"(?P<number>{_NUM})\s*(?:个\s*)?(?P<unit>{_UNITS})(?![A-Za-z])", re.I)
_CADENCE = re.compile(r"每(?:个)?(?P<unit>工作日|毫秒|秒|分钟|小时|天|日|周|星期|月|季度|年)")
_GRANULARITY = re.compile(r"(?P<unit>毫秒|秒|分钟|小时|天)级")
_PERCENT = re.compile(rf"百分之(?P<number>{_NUM})")
_UUID = re.compile(r"(?<![\da-f])[\da-f]{8}-(?:[\da-f]{4}-){3}[\da-f]{12}(?![\da-f])", re.I)
_CHAPTER_ID = re.compile(r"(?<![A-Za-z0-9_])chapter[-_][A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*(?![A-Za-z0-9_])", re.I)
_CLAUSE = re.compile(r"[^。！？!?；;\n，,]+")
_PENDING = re.compile(r"待(?:确认|核实|评估|测定|验证|调研|实测)|尚(?:未|待)|有待|未(?:提供|确认|核实|确定)|需(?:要)?(?:另行)?(?:确认|核实|评估|验证|调研|实测)|是否|能否|无法(?:判断|确定|量化评估|证明)|不能(?:仅|单凭|据此|证明)|不代表|不证明|不得据此")
_PARAMETER_NEGATOR = r"(?:严禁|不应|不得|不能|不会|无法|不可|不要|不)"
_PROHIBITED_PARAMETER_ACTION = re.compile(
    _PARAMETER_NEGATOR +
    r"(?:\s|直接|轻易|贸然|随意|擅自|擅|预先|提前|合理|据此|无依据地|"
    r"在(?:(?![。！？!?；;\n，,]|但是|但|且|并|承诺|设置|设定|制定|指定|给出|保证|确保).){1,32}(?:下|时)|"
    r"未经(?:验证|实测|测试|确认)(?:就|便)?){0,6}"
    r"(?:承诺|设置|设定|制定|指定|给出)")
# These introduce a new action, rather than a modifier of the earlier value.
# 后的一天窗口 is deliberately not a boundary; 后确认是否 is a later review.
_ACTION_BOUNDARY = (
    r"(?:随后|然后|接着|继而)(?=(?:就|便)?(?:固定(?!的)|设置|设定|配置|采用|执行|"
    r"平台|系统|本项目|现有|当前|响应|备份))|"
    r"后(?=(?:再)?(?:确认|核实|验证|检查)(?:是否|能否))")
_PROMISE_BOUNDARY = re.compile(r"但是|然而|但|并且|且|并(?!发)|而|却|同时|另外|" + _ACTION_BOUNDARY)
_NEGATED_INFERENCE = re.compile(
    r"(?:并不|不能|无法|不应|不得|不可|不)(?:据此|由此|直接|仅凭)?(?:反推|推断|推定|推导(?:出)?|推出|证明|断言)")
_CONDITION = re.compile(r"(?:^|[：:（(])\s*(?:若|如(?:果|经|需)|假设|当.+?时|在.+?(?:前提|条件)下)|(?:若|如果|假设).{0,40}(?:则|可|应|需|时|后|建议)")
_DEFINED_THRESHOLD_CONDITION = re.compile(
    r"(?:判定|告警|报警)(?:条件|规则)\s*(?:已)?(?:设定为|设为|规定为|固定为|确定为)\s*[:：]?\s*"
    r"当[^。！？!?；;\n，,]{1,180}?时")
_CANDIDATE = re.compile(r"候选|可选|备选|拟议|供.{0,8}(?:讨论|确认)|建议值|示例值")
_CONFIRM = re.compile(r"(?:经|由|须|需|待|有待).{0,15}(?:确认|核实|评估|验证|实测)|待确认|待核实|尚未确定")
_EPISTEMIC = re.compile(r"不能(?:仅|单凭|据此)|无法(?:仅|单凭|据此)|不足以证明|不(?:代表|证明|等于)|不可据此|不能将|不得将")
_NEGATED_EVIDENCE = re.compile(
    r"并非|并不|并未|否认|不(?:采用|执行|配置|保留|允许|支持|超过|满足|具备|是)|"
    r"(?:严禁|不应|不得|不能|不可|不要)(?:采用|执行|配置|保留|允许|支持|超过|满足|具备)|"
    # A forbidden value assignment or denied guarantee is not the same value
    # asserted positively. These source-only patterns do not qualify body text.
    + _PARAMETER_NEGATOR + r"\s*"
    r"(?:(?:直接|擅自|随意|提前|预先|据此)\s*){0,3}"
    rf"(?:(?:将|把)(?:(?![。！？!?；;\n，,]|{_PROMISE_BOUNDARY.pattern}).){{1,24}})?"
    r"(?:设为|设置为|设定为|固定为|保证|确保)|"
    rf"不为\s*(?={_NUM}|每(?:个)?(?:工作日|毫秒|秒|分钟|小时|天|日|周|星期|月|季度|年)|(?:毫秒|秒|分钟|小时|天)级)|"
    # Negated existence is narrower than an arbitrary occurrence of 没有/无.
    # Only an adjacent counted object is excluded; later clauses are retained.
    rf"(?:没有|不存在|无)\s*(?:(?:配置|部署|拥有|安装|运行)\s*)?{_NUM}\s*(?:台|套|(?:个\s*)?节点|个)|"
    r"(?:视为|属于|是)(?:无效|无依据|缺乏依据)(?:的)?(?:假设|推断|猜测|承诺)|"
    r"未(?:采用|部署|配置|执行)|没有(?:证据|资料)|无法证明|不能证明|不代表|不证明")
_DOCUMENT_HEADER = re.compile(r"(?m)(?=^\s*标题\s*[:：])")

# Objects and roles prevent a source version or an unrelated quantity from
# authorising a project parameter. Unknown roles require literal local evidence.
_SUBJECTS = {
    "server": r"服务器|主机",
    "business_system": rf"业务系统|[{_CN}\d]+套.{{0,8}}系统",
    "backup": r"备份|全量|增量",
    "loss": r"丢失|RPO",
    "recovery": r"恢复(?:时间|窗口|目标)|RTO",
    "retention": r"保留|留存|保存期限",
    "sampling": r"样本|抽样|采样|采集(?:频率|周期)|采集最近|最近",
    "recognition": r"识别|检测|发现|告警|响应",
    "capacity": r"容量|存储空间|磁盘|数据量|数据规模",
    "cost": r"费用|投资|预算|价格|成本|报价",
    "duration": r"工期|建设周期|实施周期|持续|观察|试运行|至少",
    "throughput": r"吞吐|并发|QPS|TPS|请求|性能",
    "port": r"端口",
    "threshold": r"阈值|上限|下限|阈值为",
    "retry": r"重试|重复执行",
    "polling": r"轮询",
    "conflict_case": r"(?:典型)?冲突案例",
}
_ROLE_PATTERNS = {key: re.compile(pattern, re.I) for key, pattern in _SUBJECTS.items()}
_EXPLICIT_NUMBER = re.compile(rf"(?:端口|阈值|上限|下限)\s*(?:为|是|设为|设置为|[:：=])?\s*(?P<number>{_NUM})(?![\d.])")
_BARE_SETTING = re.compile(
    rf"(?P<name>(?:最大|最小|当前|同时|总|活跃|空闲)?(?:并发连接数|连接数|并发数|线程数|进程数|副本数|分区数|节点数|服务器数|用户数|账户数|设备数|重试次数|轮询次数|计数)|"
    rf"[\u3400-\u9fffA-Za-z_]{{0,12}}指标)\s*(?:为|是|设为|设置为|固定为|[:：=])?\s*(?P<number>{_NUM})(?![\d.])")
_SCOPED_OBJECT = re.compile(
    r"(?:业务系统|系统|部门|数据库)[A-Za-z0-9_-]{1,16}|"
    r"[\u3400-\u9fffA-Za-z0-9_-]{1,24}?(?:数据库|部门|系统)(?:[A-Za-z0-9_-]{1,16})?")
# Shared count predicates bind the same noun in authored text and evidence.
_COUNT_RELATION = r"(?:对象数量|数量|总数)"
_COUNTED_SYSTEM_NOUN = r"系统(?:[A-Za-z0-9_-]{1,16})?"
_GENERIC_SERVER_NOUN = r"(?:(?:现有|既有|数据)\s*)*(?:服务器|主机)"
_COUNT_SOURCE_PROVISION = r"(?:资料|材料|清单|事实|文档|输入)(?:中)?提供(?:的)?"
# Complete reporting/count predicates do not remove unknown server types,
# ownership, procurement or use modifiers from the counted noun.
_COUNT_REFERENCE_PREFIX = re.compile(
    r"\s*(?:(?:本项目|项目|当前|现有|既有|上述|该)\s*)*"
    r"(?:(?:没有|不存在|无)\s*)?")
_SERVER_OBJECT_COUNT_PREFIX = re.compile(
    r"\s*(?:(?:本项目|项目|当前|现有|既有|上述|该)\s*)*"
    rf"(?:{_COUNT_SOURCE_PROVISION}\s*)?(?P<noun>{_GENERIC_SERVER_NOUN})"
    r"\s*对象数量\s*(?:为|是|共|[:：])?\s*")
_SERVER_REVERSE_COUNT_SUFFIX = re.compile(
    rf"\s*(?:为|是)\s*(?:{_COUNT_SOURCE_PROVISION}\s*)?"
    rf"(?P<left>[“‘\"']?){_GENERIC_SERVER_NOUN}(?P<right>[”’\"']?)"
    rf"\s*{_COUNT_RELATION}\s*")
_COUNT_ADDITION_VERB = r"(?:新增|新购|采购|购置|扩容|补充|增购)"
_SERVER_COUNT_PREFIX = re.compile(
    r"(?:服务器|主机)(?:数量)?\s*(?:为|是|共|[:：])?\s*$|"
    rf"(?P<total>(?:(?<![\u3400-\u9fffA-Za-z0-9_-])|(?<=的)|(?<={_COUNT_ADDITION_VERB}))"
    r"(?:本项目|项目)?"
    r"(?:(?:现有|既有|数据)\s*)*(?:服务器|主机)\s*总数\s*(?:为|是|共|[:：])?\s*)$")
_COUNT_ADDITION = re.compile(
    rf"{_COUNT_ADDITION_VERB}(?:的)?\s*(?=[“‘\"']?{_NUM}|"
    r"[“‘\"']?(?:(?:现有|既有|数据)\s*)*(?:服务器|主机|(?:内部)?业务系统))")
_NEGATED_COUNT_ADDITION = re.compile(r"(?:没有|未|" + _PARAMETER_NEGATOR + r")\s*" + _COUNT_ADDITION.pattern)
# A report's subject/predicate is outside the following counted noun. Require
# an explicit reporting construction, not an arbitrary verb inside a name.
_COUNT_REPORT = re.compile(
    r"^\s*(?:(?:当前|现有|已提供|本项目|项目|已有|相关|这些|上述)\s*)*"
    r"(?:资料|材料|清单|事实|文档|输入)(?:中)?"
    r"(?:(?:仅|已|已经)(?:明确|确认|提及|列明|记载|表明)(?:了)?|"
    r"(?:明确|确认|提及|列明|记载|表明)了)\s*")
_NEUTRAL_BUSINESS_ALIASES = frozenset(
    modifier + noun for modifier in ("独立", "独立的", "彼此独立的", "相互独立的")
    for noun in ("业务系统", "内部业务系统")) | {"特定业务系统"}
_NEUTRAL_BUSINESS_OBJECT = "(?:" + "|".join(sorted(_NEUTRAL_BUSINESS_ALIASES, key=lambda label: (-len(label), label))) + ")"
_SYSTEM_GROUP_NOUNS = {"系统", "业务系统", "内部业务系统"} | _NEUTRAL_BUSINESS_ALIASES
_SYSTEM_GROUP_NOUN = "(?:" + "|".join(sorted(_SYSTEM_GROUP_NOUNS, key=lambda label: (-len(label), label))) + ")"
_SYSTEM_STOP_CONDITION = re.compile(
    rf"\s*(?P<intro>当|若|如果)(?P<prefix>[^。！？!?；;\n，,]{{0,24}}?)"
    rf"(?P<count>{_NUM}\s*套)\s*(?P<object>[\u3400-\u9fffA-Za-z0-9_-]{{0,24}}?系统(?:[A-Za-z0-9_-]{{1,16}})?)"
    r"\s*停机(?:维护)?(?P<when>时)?\s*")
_SYSTEM_REMAINDER = re.compile(
    rf"\s*(?P<prefix>[^。！？!?；;\n，,]{{0,40}}?)(?:其余|其他|剩余)"
    rf"(?P<count>{_NUM}\s*套)\s*(?P<object>[\u3400-\u9fffA-Za-z0-9_-]{{0,24}}?系统(?:[A-Za-z0-9_-]{{1,16}})?)")
_SYSTEM_PHASE = re.compile(rf"第{_NUM}(?:阶段|期)")
_NEGATED_SYSTEM_PHASE_ALLOCATION = re.compile(
    _PARAMETER_NEGATOR + rf"\s*(?:(?:在|于)第{_NUM}(?:阶段|期)\s*)?"
    r"(?:直接|擅自|随意)?(?:接入|扩展至)")
_UNIVERSAL_OBJECT = re.compile(
    rf"(?:所有|全部|各(?:个|套)?|每(?:一)?(?:个|套))(?:{_NEUTRAL_BUSINESS_OBJECT}|(?:内部)?(?:业务系统|应用系统|信息系统|系统|业务部门|部门|数据库))"
    r"(?![A-Za-z0-9_-]|中|里)")
_ALLOCATION_OBJECT = rf"(?:{_NEUTRAL_BUSINESS_OBJECT}|(?:内部)?(?:业务系统|源系统|应用系统|信息系统|系统|业务部门|部门|数据库))"
_PER_OBJECT = re.compile(rf"(?:每(?:一)?(?:个|套)?|各(?:个|套)?){_ALLOCATION_OBJECT}(?![A-Za-z0-9_-]|中|里)")
# An omitted allocation object remains unresolved, rather than becoming a total.
_ELIDED_PER_OBJECT = re.compile(
    rf"(?:每(?:一)?套|各套)(?=\s*(?:配置|部署|配备|拥有|使用)\s*(?:{_NUM}|$))")
_COLLECTIVE_OBJECT = re.compile(
    rf"(?:所有|全部){_ALLOCATION_OBJECT}\s*(?:共(?:有|用|享|同|配置|部署)?|合计|总计|总共)")
_DEFICITS = re.compile(
    r"数据孤岛|缺乏统一(?:的)?(?:认证|身份|数据汇聚|汇聚|权限|登录|标准)|"
    r"(?:格式|数据标准|字段|接口|口径).{0,12}(?:显著差异|差异显著|不一致)|"
    r"(?:显著差异|差异显著).{0,8}(?:格式|字段|接口|口径)|"
    r"(?:系统|数据).{0,8}(?:独立运行|分散存储|数据分散)|"
    r"(?:缺乏|缺少|没有|尚无|未建立).{0,12}(?:认证|权限|审计|备份|监控|汇聚通道)|"
    r"(?:审计|备份|权限|监控).{0,8}(?:不完善|缺失|不足)"
)
_NEGATED_STANDARD_DEFICIT = re.compile(
    r"(?:并非|并不|不是|不)(?:(?:现有|当前|既有)?(?:内部)?(?:业务系统|系统))?"
    r"缺乏统一(?:的)?标准")
_STANDARD_PROBLEM_STATUS = re.compile(
    r"\s*(?:本项目|项目)的(?:核心)?必要性在于解决"
    r"(?P<proposition>(?:现有|当前|既有)[^。！？!?；;\n，,]{1,180}?缺乏统一(?:的)?标准)"
    r"的问题\s*")
_PROJECT = re.compile(r"现有|当前|目前|既有|本项目|项目|业务系统|这些系统|这三套|三套系统")
_CAPABILITY = re.compile(r"仲裁|高可用|可用性|性能|吞吐|可靠性|容灾|无丢失|无重复|零丢失|恢复目标|故障切换|自动切换")
_CERTAINTY = re.compile(
    r"不足以|无法(?!(?:(?:客观|准确|定量|有效|合理|全面|直接|可靠)(?:地)?)*"
    r"(?:量化|评估|判断|确定|证明|估算|确认|测定))|"
    r"不能实现|已实现|已满足|确保|保证|必然|一定|能够满足|即可实现|可实现|可满足")
_RECOVERY_OBJECTIVE_MIXUP = re.compile(
    r"恢复时间目标\s*[（(]\s*RTO\s*[/、和及]\s*RPO|"
    r"RTO\s*[/、]\s*RPO.{0,8}(?:均为|都是|统称为|指的是|即为|是)\s*恢复时间目标", re.I)
_REFERENCE_IDENTIFIERS = re.compile(
    r"(?:NIST\s*SP|ISO(?:\s*/\s*IEC)?|IEC|IEEE|RFC|GB\s*/?\s*T?)\s*\d+(?:[-–—.:/]\d+)*|"
    r"(?:PostgreSQL|(?:Apache\s+)?Kafka(?:\s+Connect)?|Great\s+Expectations|Prometheus)"
    r"\s*(?:官方(?:文档)?|文档|(?:框架)?自)?\s*[（(]?\s*(?:版本|v)?\s*\d+(?:\.\d+)*", re.I)
# Fixed protocol/metric names carry lexical digits, not project scalar values.
# Their complete local spans do not authorise the same numeral elsewhere.
_LEXICAL_NUMERIC_IDENTIFIERS = re.compile(
    r"(?<![A-Za-z0-9_])(?:OAuth2(?:\.0)?|P(?:95|99)|UTF-8|MD5|SHA256)(?![A-Za-z0-9_])", re.I)
_CONCEPT_SENTENCES = re.compile(r"[^。！？!?；;\n]+")
_LOW_CARDINALITY_SMALL_FILE_CAUSE = re.compile(
    r"(?:低基数(?:字段|分区键|分区字段|键|列)?|(?:分区键|分区字段|分区依据).{0,8}低基数)"
    r".{0,20}(?:导致|造成|产生|引发|带来|形成|会使|会产生|可能导致|容易导致)"
    r".{0,10}(?:大量|过多|很多|众多).{0,6}(?:小文件|小分区|分区)"
)
_POSTGRESQL_REFERENCE = re.compile(r"(?<![A-Za-z0-9_])(?:PostgreSQL|Postgres)(?![A-Za-z0-9_])", re.I)
_OTHER_DATABASE_REFERENCE = re.compile(
    r"(?<![A-Za-z0-9_])(?:Oracle|MySQL|MariaDB|SQL\s*Server|SQLite|ClickHouse|DB2)(?![A-Za-z0-9_])|甲骨文", re.I)
_READONLY_TABLESPACE = re.compile(r"(?:只读(?:的)?表空间|表空间.{0,8}只读)")
_TABLESPACE_ACTION = re.compile(
    r"(?:配置|设置|设为|标记为|转为|变为|归档|存储|保存|迁移).{0,18}(?:只读(?:的)?表空间|表空间.{0,8}只读)|"
    r"(?:只读(?:的)?表空间|表空间.{0,8}只读).{0,18}(?:配置|设置|设为|标记|归档|存储|保存|迁移)"
)
_KAFKA_CONNECT = re.compile(r"(?:Kafka.{0,32}Connect|Connect.{0,32}Kafka|Connect\s*框架)", re.I)
_EXACTLY_ONCE = re.compile(r"(?:端到端)?恰好一次|exactly[ -]?once", re.I)
_ALERTMANAGER = re.compile(r"(?<![A-Za-z0-9_])Alertmanager(?![A-Za-z0-9_])", re.I)


def content_quality_policy_hash():
    """Invalidate stored review/cache decisions whenever this policy changes."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def generation_quality_rules():
    """Rules to append to generation and its existing correction request."""
    return (
        "区分已提供项目事实、公开通用参考、条件建议和待确认事项。拟统一不能反推现有数据孤岛、"
        "统一认证缺失、接口或数据格式显著差异；资料未提供不等于能力不存在。公开技术资料不能证明项目现状、"
        "既定选型或性能承诺。中文和阿拉伯数字都属于参数：数量、周期、时效、容量、费用、阈值、端口、"
        "备份频率、保留期和秒级等性能均须对应具体项目依据。无依据时，在该具体断言中明确待确认，"
        "或给出可核验且逐项待确认的条件设计建议；建议、例如、默认值本身不构成依据，固定周期示例仍需逐项待确认。"
        "对未提供的项目运行数值，默认写确认方法与所需资料字段，不主动给固定候选值。"
        "只有建议或试运行措辞不能擅定每日全量、每小时增量等具体运行周期；"
        "无同一对象与用途的项目依据时，逐项写周期待确认、所需字段与验证方法。"
        "整章或整段泛泛免责声明不能覆盖其他固定参数。业务系统和服务器数量只能沿用当前输入已提供的事实，"
        "引用数量时保留资料中的对象名称与范围，不能把服务器数量改写成物理设备数、节点数、投票成员数或副本数；"
        "物理形态、部署角色、复制与仲裁拓扑均须另有依据，否则逐项待确认。"
        "已有设备总数量不代表用途拆分、主备或冷热部署已确认；每部分职责必须有项目依据，"
        "否则明确该职责未确认并说明确认步骤，不能直接把设备分别指定为热数据处理与冷数据归档。"
        "不得只按服务器数量断言仲裁不足或已保证高可用。标题序号和明确归属公开文档的标准/版本编号"
        "不是项目参数，来源可核验且明确归属公开文档的标准或软件版本编号仍可正常引用；"
        "该编号不能作为项目运行数值的依据。UUID、内部chapter ID只用于元数据source_ids/chapter_id，不得写入正文。"
        "核对技术概念与保障边界：RTO为恢复时间目标，RPO为恢复点目标；CDC或时间戳识别变更记录，"
        "不能单独判断数据质量合格。Schema及对象命名规范不自动保证跨系统业务标识值唯一；"
        "普通哈希比对依赖可信校验基准及权限保护，不能独自保证防篡改。备份生成时间与故障恢复时间分开测量。"
        "已设定的判定或告警条件中，即使使用当或例如，具体比例、持续时间及最少案例数仍须项目依据；"
        "否则阈值、观察窗口、判定规则和案例数量逐项待确认，并按实测如实记录发现或未发现的问题。"
        "Schema注册中心是数据契约与模式兼容检查项，不是Kafka Connect恰好一次能力的通用必要条件。"
        "OAuth2.0是授权框架，不能单独列为身份认证协议或认证证明；身份流程与用户目录分开核查。"
        "缺少更新时间戳或自增标识不代表只能全量比对；另行调查日志CDC、变更事件与接口，"
        "自增标识不能完整识别已有记录的更新和删除。RTO依据业务中断或恢复时间，RPO依据恢复点或损失窗口。"
        "服务器数量不能决定冷热分层必须外接存储；核查已有介质、容量及访问特征，区分逻辑分区和物理分层。"
        "I/O争用须核查I/O控制、作业并发或调度并共载测试，不能仅用CPU和内存配额宣称问题已解决。"
        "准确性需与业务真值或权威记录比对；完整性检查应有记录与必填值覆盖，"
        "格式、范围及枚举检查属于有效性，关联规则须标清参照完整性或一致性；不能互相替代验证结论。"
        "RTO/RPO目标由业务确认，压力测试或恢复演练记录实际耗时及可恢复数据位置，用于验证是否满足目标，"
        "不能按当前实测水平直接填写或确定业务目标。数据库复制、主备角色管理和网络入口接管分开核查；"
        "Keepalived的健康检查、VRRP或虚拟IP接管不能单独证明复制一致性、安全主备提升或旧主隔离。"
        "审计事件及字段按最小必要原则分类确认，SQL模板、操作类型及行数可评估，不默认记录原始SQL参数或查询结果。"
        "密码、访问令牌、密钥等凭据应排除，敏感业务字段按已确认规则最小化或脱敏，并核验日志访问和保留要求。"
        "哈希链为待评估的完整性检测机制，须明确可信锚点、受保护校验基准及权限隔离，"
        "验证修改、删除或截断是否可检测；采用哈希链本身不能证明防篡改能力已经成立。"
        "分区键基数与小文件/分区数量的关系须结合分区方式、键基数和分布、数据量及读写负载判断；"
        "低基数本身不是导致大量小文件的通用理由，过多分区或小文件风险须核验具体条件。"
        "不能在未说明具体机制条件时写低基数分区键可能导致大量小文件；"
        "仅尾随并非绝对规律或需验证仍未纠正该因果说法。"
        "小文件风险应结合写入批次、分区粒度、数据分布与合并策略等具体条件分析并验证。"
        "跨分区扫描性能不得写成必然显著下降，应结合分区裁剪、执行计划、数据分布和查询负载验证。"
        "PostgreSQL表空间用于存储位置与隔离，不是原生可配置的只读表空间；SQL写入权限、只读事务和归档防篡改是不同控制，须分别核验。"
        "Kafka Connect具备恰好一次处理能力的支持路径，但适用性取决于connector、模式与配置，端到端边界须验证；"
        "不得笼统否定该框架支持能力。Alertmanager的inhibition用于抑制符合条件的相关告警，"
        "与告警分组聚合/去重及repeat_interval重复通知控制不同；区分单个告警组本次通知合并和后续重复提醒。"
    )


def content_review_prompt():
    """Instructions for complex facts beyond the deterministic guard's scope."""
    return (
        "独立复核所有实际发送的正文，并逐项给出可定位的paragraph/claim/依据与纠正要求。"
        + generation_quality_rules()
        + "必须核对主语、量值、用途和证据性质，不能因相同数字见于其他来源而视为有据。"
        "核对无数字的现状、因果、选型、可行性与可靠性断言；条件建议不得写成既成事实。"
        "source_ids及chapter_id是元数据，其中UUID本身不构成正文违规。"
        "只按review_contract权威全文计数判篇幅，不按sample或片段长度判全文不足；"
        "sample_truncated只代表未发送后文，不能据此判实际正文截断。"
        "issues是实际缺陷清单，不是逐项审查笔记：自判合规、未发现实质错误、未来可能出现的错误、"
        "仅需人工核查或片段未发送完整，都不能列为已发现问题；真实问题必须保留并定位。"
        "实施步骤、拟建立的方案模块及方案中的最小权限等安全控制，不等于声称它们已经存在或是既有制度。"
        "明确用例如或条件描述的适用场景不等于声称本项目已有该业务；未经依据的最终选型仍须拦截。"
        "不能单凭设备数量证明高可用等保障边界，不等于断言方案必然不可行。"
        "已批准待确认资料中的具体缺项，可支持对应资料尚未提供的边界说明；不要因跨批未发送上下文而反推错误。"
        "抽样复核须如实标记范围并保留人工全文复核要求；未见问题不代表未发送全文通过。"
        "仅对发送内容与可信依据可证明的实质问题报issue，未提供信息本身不是已证实的缺陷。"
        "全篇复核分区因果是否依据分区键基数、分布、分区方式及负载；不要把低基数泛化为大量小文件成因，"
        "也不要断言跨分区扫描必然显著变慢。若涉及PostgreSQL，区分表空间存储隔离、SQL写入权限、只读事务和归档防篡改；"
        "若涉及Kafka Connect，核实connector、模式、配置与端到端恰好一次边界；若涉及Alertmanager，区分inhibition、"
        "分组聚合/去重和repeat_interval；区分每个告警组本次通知合并成一条与后续重复提醒，"
        "不要把inhibition说成同类错误永久只通知一次。正式生产割接前完成验证，并闭环遗留问题。"
        "逐项复核已设定判定条件内的中文或阿拉伯数值、观察窗口及验收案例配额；条件句或例如不能自动批准固定值。"
        "复核模式注册与处理语义、身份认证与授权、哈希及受保护可信基准、标记轮询与日志CDC的边界。"
        "复核RTO/RPO各自业务输入、服务器数量与存储分层、I/O风险与实际控制项，以及质量维度与验证依据。"
        "对这些复杂因果须定位实际错误和缺失机制，不能仅凭话题词或未知部署条件判错。"
        "复核业务恢复目标与压力测试或恢复演练测量值是否被混同，数据库复制及角色管理与网络入口接管是否被混同。"
        "复核SQL审计候选是否明确字段最小化、原始参数或结果边界及凭据排除，不能据未知隐私条件认定已经泄露。"
        "复核哈希链完整性结论是否绑定可信锚点、受保护基准及访问隔离；同段无关基准描述不能代替该机制条件。"
    )


def _alertmanager_concept_mismatch(sentence):
    """Check an asserted inhibition relationship, not nearby feature names.

    Commas and contrast clauses delimit corrections: a correct distinction in
    one clause must not excuse a grouping or permanent-once claim in another.
    """
    inhibition = r"(?:抑制规则|告警抑制|inhibition)(?:机制|功能|本身)?"
    grouping = r"(?:聚合|分组|去重)"
    relation = re.compile(
        rf"{inhibition}\s*(?:(?:可(?:以)?|能够|能|会)?(?:用于|负责|实现|完成|提供|进行|执行|承担|支持|使|让|将|对)|等同于|就是|是).{{0,18}}{grouping}|"
        rf"{inhibition}\s*{grouping}|"
        rf"{grouping}(?:功能|机制|操作|处理|工作|能力|过程|通知)?\s*(?:可(?:以)?|能够|能)?"
        rf"(?:通过|由|依靠|依赖|借助|使用|采用|配置|利用)\s*(?:配置)?{inhibition}", re.I)
    once = re.compile(r"(?:仅|只|仅仅).{0,8}(?:发送|通知|推送).{0,5}一次|(?:发送|通知|推送).{0,5}仅一次")
    labels_same_error = bool(re.search(
        r"同一数据源|相同数据源|连续相同|相同(?:错误|告警)|重复(?:错误|告警)", sentence))
    for clause in re.split(
            r"[，,]|但是|然而|但(?=\S)|而是|(?<!从)而(?=\S)|却|"
            r"(?:并且|并|以及|及|且)(?=(?:通过|用|由|采用)?(?:group_by|repeat_interval|inhibition|抑制规则|告警抑制))",
            sentence, flags=re.I):
        for match in relation.finditer(clause):
            before, claim, after = clause[:match.start()], match.group(), clause[match.end():]
            prohibited = re.search(r"(?:不应|不得|不能|不要|避免)(?:将|把|以)?\s*$", before)
            negated = re.search(r"不是|并非|不包括|不进行|不负责|不用于|不支持|不能|不应|不得|不等于|不等同于|不同于|区别于", claim)
            corrected = re.match(r".{0,12}(?:是|属于)?(?:错误(?:说法|表述|观点)|误称|不准确(?:表述)?)", after)
            if not (prohibited or negated or corrected):
                return True
        scoped_group_notice = bool(re.search(
            r"(?:(?:同一|相同|每个)告警组|group_by).{0,18}(?:本次|单次).{0,10}(?:通知|提醒).{0,12}(?:合并|聚合|一条|一次)|"
            r"(?:本次|单次).{0,10}(?:通知|提醒).{0,18}(?:(?:同一|相同|每个)告警组|group_by).{0,12}(?:合并|聚合|一条|一次)", clause, re.I))
        for match in once.finditer(clause):
            before = clause[:match.start()]
            negated = re.search(r"(?:不代表|不保证|不能保证|不意味着|不等于|不是|并非|不能|不应|不得).{0,24}$|不\s*$", before)
            corrected = re.match(r".{0,12}(?:是|属于)?(?:错误(?:说法|表述|观点)|误称|不准确(?:表述)?)", clause[match.end():])
            if labels_same_error and not (scoped_group_notice or negated or corrected):
                return True
    return False


def _asserted_concept_relation(sentence, match):
    """Test negation at this relation, not an unrelated earlier disclaimer."""
    before = re.split(r"[，,]|但是|然而|但|而是|却", sentence[:match.start()])[-1]
    after = sentence[match.end():]
    return not (_within_spans(match.start(), match.end(), _negated_inference_spans(sentence))
                or re.search(r"(?:不应|不得|不能|不要|避免)(?:将|把|声称)?\s*$", before)
                or re.search(r"并非|并不|不是|不依赖|不属于|不等于|不能|不应|不得", match.group())
                or re.match(r"\s*[”’\"']?\s*(?:这一|该)?(?:说法|表述|观点)?(?:是|属于)?(?:错误|误称|不准确)", after))


def _protected_hash_baseline(sentence, match):
    """Bind a protected, isolated baseline to this specific log hash check."""
    before = re.split(r"[，,]|但是|然而|但|而是|却", sentence[:match.start()])[-1]
    return bool(re.fullmatch(
        r"\s*(?:已(?:经)?)?(?:以|用)(?:独立)?隔离(?:且|并)受保护的可信(?:校验)?基准"
        r"(?:核验|校验|比对)(?:审计)?日志(?:的)?\s*", before))


def _bounded_concept_relationships(sentence, previous):
    """Check explicit relations, keeping their technical topics usable."""
    findings = []
    if _KAFKA_CONNECT.search(sentence) and _EXACTLY_ONCE.search(sentence):
        dependency = re.compile(
            r"(?:其适用性(?:高度)?|(?:而是)?高度|恰好一次(?:处理)?(?:语义|能力)?(?:高度)?)"
            r"依赖于?[^。！？!?；;\n]{0,85}(?:Schema\s*注册中心|Schema\s+Registry)", re.I)
        if any(_asserted_concept_relation(sentence, m) for m in dependency.finditer(sentence)):
            findings.append((sentence, "Schema注册中心用于数据契约和模式兼容；不要列为Kafka Connect恰好一次能力的通用必要条件。"))
    classification = re.compile(
        r"身份认证协议\s*[（(](?:如|例如)?[^（）()。！？!?；;\n]{0,60}OAuth\s*2(?:\.0)?|"
        r"OAuth\s*2(?:\.0)?\s*(?:本身)?(?:是|属于|作为|当作|列为)\s*身份认证(?:协议|框架|证明)", re.I)
    # Exclusion is local to the OAuth example, not a generic relation negator.
    if any(not re.search(r"(?:不包括|不含|排除)\s*OAuth\s*2(?:\.0)?$", m.group(), re.I)
           and not re.match(r"\s*[）)]\s*(?:这一|该)?(?:说法|表述|观点)(?:是|属于)?(?:错误|误称|不准确)",
                            sentence[m.end():])
           and _asserted_concept_relation(sentence, m) for m in classification.finditer(sentence)):
        findings.append((sentence, "OAuth2.0是授权框架；身份认证流程、用户目录和资源授权分开核查，不能单凭OAuth2.0证明身份认证。"))
    hash_guarantee = re.compile(
        r"(?P<hash_check>(?:完整性校验)?哈希值\s*[，,]\s*(?:确保|保证)(?:审计)?日志(?:未被|没有被)恶意篡改)|"
        r"(?P<hash_only>(?:仅凭|仅靠|仅依靠|普通)[^。！？!?；;\n，,]{0,18}哈希(?:值|比对)"
        r"[^。！？!?；;\n，,]{0,12}(?:确保|保证)[^。！？!?；;\n，,]{0,12}(?:防篡改|未被恶意篡改))")
    if any(_asserted_concept_relation(sentence, m)
           and not (m.group("hash_check") and _protected_hash_baseline(sentence, m))
           for m in hash_guarantee.finditer(sentence)):
        findings.append((sentence, "哈希值只能作为完整性检测证据；还须明确受保护的可信基准、访问隔离及校验和篡改测试，不能独自确保防篡改。"))
    only_full = re.compile(
        r"(?:若|如果)(?:缺乏|缺少|没有)(?:此类字段|标记字段|更新时间戳(?:或自增ID)?)"
        r"\s*[，,]\s*(?:则)?\s*全量比对(?:将)?(?:成为|是)唯一(?:可行)?(?:方案|路径)")
    if (re.search(r"更新时间戳|自增ID|标记字段", previous + sentence)
            and any(_asserted_concept_relation(sentence, m) for m in only_full.finditer(sentence))):
        findings.append((sentence, "缺少标记字段不排除日志CDC、变更事件或其他接口；全量比对只能在核查可用路径后作为待评估方案。"))
    goal = (r"(?:恢复(?:时间|点)目标(?:\s*[（(]\s*(?:RTO|RPO)\s*[）)])?|"
            r"(?:RTO|RPO)(?:\s*(?:和|与|及|、|/)\s*(?:RTO|RPO))*\s*(?:的)?目标(?:值)?)")
    measured_goal = re.compile(
        rf"{goal}(?:\s*(?:、|及|和|与)\s*{goal})*(?:的)?(?:数值|目标值)?"
        r"(?:\s*[，,]\s*(?:均|都)\s*|\s*)(?:需|须|应)?(?:在(?:实际)?压力测试后)?"
        r"(?:根据|按)(?:压力测试(?:实测)?|实测)结果(?:填写|确定|设定)", re.I)
    if any(_asserted_concept_relation(sentence, m) for m in measured_goal.finditer(sentence)):
        findings.append((sentence, "RTO/RPO是业务确认的恢复目标；测试测量实际耗时和可恢复位置以验证达标，不能直接用实测结果确定目标。"))
    database_tool = re.compile(
        r"数据库集群管理工具\s*[（(](?:如|例如)?[^（）()。！？!?；;\n]{0,60}Keepalived(?![A-Za-z0-9_])|"
        r"Keepalived\s*(?:是|属于|作为|用作)\s*数据库集群管理工具", re.I)
    if any(not re.search(r"(?:不包括|不含|排除)\s*Keepalived$", m.group(), re.I)
           and not re.match(r"\s*[）)]\s*(?:这一|该)?(?:说法|表述|观点)(?:是|属于)?(?:错误|误称|不准确)",
                            sentence[m.end():])
           and _asserted_concept_relation(sentence, m) for m in database_tool.finditer(sentence)):
        findings.append((sentence, "Keepalived的网络入口接管与健康检查不等于数据库复制及主备角色管理；分别核查机制和工具。"))
    chain_without_anchor = re.compile(
        r"哈希链(?:技术)?\s*(?:无需|不需要)(?:受保护的)?可信锚点"
        r"\s*(?:就|即可)?(?:保障|确保|保证)(?:日志)?完整性")
    if any(_asserted_concept_relation(sentence, m) for m in chain_without_anchor.finditer(sentence)):
        findings.append((sentence, "哈希链完整性检测须说明可信锚点、受保护基准及隔离；不能声称不需要可信锚点即可提供保障。"))
    return findings


def _technical_concept_mismatches(paragraph, source_context):
    """Catch a few established, high-confidence technical concept reversals."""
    source_text = _public_text(source_context)
    findings = []
    database_scope = None
    previous = ""
    for match in _CONCEPT_SENTENCES.finditer(paragraph):
        sentence = match.group().strip()
        if not sentence:
            continue
        findings.extend(_bounded_concept_relationships(sentence, previous))
        previous = sentence
        sentence_has_postgresql = bool(_POSTGRESQL_REFERENCE.search(sentence))
        sentence_has_other_database = bool(_OTHER_DATABASE_REFERENCE.search(sentence))
        if sentence_has_postgresql:
            database_scope = "postgresql"
        elif sentence_has_other_database:
            database_scope = "other"

        for causal_claim in _LOW_CARDINALITY_SMALL_FILE_CAUSE.finditer(sentence):
            if not re.search(r"不会|并非|并不|不是|不一定|不必然|不总会|未必|错误(?:说法|表述|观点)|误称|不准确(?:表述)?|避免|是否", causal_claim.group()):
                findings.append((sentence,
                    "低基数不是导致大量小文件的通用原因；应结合分区方式、键基数和分布、数据量及读写负载核验分区与小文件风险。"))

        has_postgresql_context = (sentence_has_postgresql or (
            not sentence_has_other_database and database_scope != "other"
            and (database_scope == "postgresql" or _POSTGRESQL_REFERENCE.search(source_text))))
        if (has_postgresql_context and _READONLY_TABLESPACE.search(sentence)
                and _TABLESPACE_ACTION.search(sentence)
                and not re.search(r"错误(?:说法|表述|观点)|误称|不准确(?:表述)?|并非|并不|并无|不是|没有|不等于|区别于|不支持|不提供|不能|不应|不得|无法|不可|未必", sentence)):
            findings.append((sentence,
                "PostgreSQL表空间用于存储位置与隔离，并非原生只读表空间配置；分别说明SQL写入权限、只读事务或归档防篡改控制。"))

        if _KAFKA_CONNECT.search(sentence) and _EXACTLY_ONCE.search(sentence):
            denies_support = (
                re.search(r"(?:Kafka\s+)?Connect(?:框架)?\s*(?:本身)?(?:并)?(?:不支持|不具备|不提供|未提供|没有).{0,18}(?:恰好一次|exactly[ -]?once)", sentence, re.I)
                or re.search(r"(?:恰好一次|exactly[ -]?once).{0,18}(?:并非|并不|不是|不属于).{0,20}(?:框架|原生|内置|自带).{0,8}(?:功能|能力|支持)?", sentence, re.I)
            )
            if denies_support and not re.search(r"错误(?:说法|表述|观点)|误称|不准确(?:表述)?|不应将|不要将|不能将|并非事实", sentence):
                findings.append((sentence,
                    "Kafka Connect有恰好一次能力的支持路径；核验connector、处理模式、配置及端到端边界，避免笼统否定框架支持。"))

        if _ALERTMANAGER.search(sentence) and re.search(r"抑制规则|告警抑制|inhibition", sentence, re.I):
            if _alertmanager_concept_mismatch(sentence):
                findings.append((sentence,
                    "Alertmanager inhibition用于抑制符合条件的相关告警；group_by可将单个告警组本次通知合并，repeat_interval控制后续重复提醒。区分这些边界，避免笼统承诺仅一次。"))
    return findings


def _number(value):
    try:
        return Decimal(value)
    except InvalidOperation:
        pass
    digits = dict(zip("零〇一二两三四五六七八九", (0, 0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9)))
    integer, _, fraction = value.partition("点")
    total = section = current = 0
    for char in integer:
        if char in digits:
            current = current * 10 + digits[char]
        elif char in "十百千":
            section += (current or 1) * {"十": 10, "百": 100, "千": 1000}[char]
            current = 0
        elif char in "万亿":
            section += current
            current = 0
            if char == "万":
                section *= 10000
            else:
                total = (total + section) * 100000000
                section = 0
    result = Decimal(total + section + current)
    if fraction:
        result += Decimal("0." + "".join(str(digits[c]) for c in fraction))
    return result


def _unit(value):
    return {"秒钟": "秒", "日": "天", "星期": "周", "个月": "月", "％": "%"}.get(value, value).lower()


def _clauses(text):
    clauses = []
    joins = re.compile(
        r"但是|然而|但(?=\S)|(?:而|却|并且|且|并|以及|及)(?=(?:是否|能否|平台|系统|本项目|现有|当前|目前|接口|日志|交易|业务|数据|响应|性能|吞吐|可靠性|可用性|容量|阈值|端口|并发|连接数|指标|线程数|副本数|分区数|重试|轮询|采用|执行|配置|固定|必须|观察|允许|确保|保证|已实现|已满足|已保证|可实现|能够满足|不能实现|无法(?:实现|达到|满足|保证)|保留|备份|全量|增量|每(?:个)?(?:工作日|毫秒|秒|分钟|小时|天|日|周|星期|月|季度|年)))|"
        + _ACTION_BOUNDARY
    )
    for match in _CLAUSE.finditer(text):
        start = 0
        for join in joins.finditer(match.group()):
            if join.start() > start:
                clauses.append((match.group()[start:join.start()], match.start() + start))
            start = join.end()
        if start < len(match.group()):
            clauses.append((match.group()[start:], match.start() + start))
    return clauses


def _conditional_system_remainders(text):
    """Locate a count after a directly adjacent system-stop condition.

    Recognition preserves invalid names, counts and predicates as rejected
    relations; it does not qualify the entire clause or authorize a rollout.
    """
    clauses = _clauses(text)
    relations = {}
    for position, (clause, offset) in enumerate(clauses[:-1]):
        condition = _SYSTEM_STOP_CONDITION.fullmatch(clause)
        if not condition:
            continue
        following, following_offset = clauses[position + 1]
        separator = text[offset + len(clause):following_offset]
        remainder = _SYSTEM_REMAINDER.match(following)
        if separator not in {"，", ","} or not remainder:
            continue
        relations[(following_offset + remainder.start("count"),
                   following_offset + remainder.end("count"))] = {
            "condition_offset": offset, "consequence_offset": following_offset,
            "condition_count": _number(re.sub(r"\s*套$", "", condition.group("count"))),
            "remainder_count": _number(re.sub(r"\s*套$", "", remainder.group("count"))),
            "condition_object": condition.group("object"), "remainder_object": remainder.group("object"),
            "valid_predicate": (condition.group("prefix") in {"", "某"}
                                and (condition.group("intro") != "当" or condition.group("when"))
                                and not remainder.group("prefix").strip()
                                and bool(re.fullmatch(r"\s*的数据流不应(?:受到|被)?阻塞\s*",
                                                      following[remainder.end():]))),
        }
    return relations


def _conditional_remainder_supported(relation, evidence):
    """Ground only this isolation-scenario count in the same confirmed group."""
    if (not relation["valid_predicate"] or relation["condition_count"] != 1
            or relation["condition_object"] not in _SYSTEM_GROUP_NOUNS
            or relation["remainder_object"] not in _SYSTEM_GROUP_NOUNS
            or relation["remainder_count"] <= 0):
        return False
    totals = set()
    for fact, parameters in evidence:
        if _COUNT_ADDITION.search(fact) or re.search(r"阶段|分期", fact):
            continue
        for parameter in parameters:
            if parameter[2][1:] != ("套", "quantity") or parameter[3] != {"business_system"}:
                continue
            if _system_phase_scope(parameter, fact):
                continue
            # A counted data/finance system or an allocation is not the total
            # of this generic business-system group, even with the same value.
            tail_noun = re.match(rf"\s*{_SYSTEM_GROUP_NOUN}(?![\u3400-\u9fffA-Za-z0-9_-])",
                                 fact[parameter[1]:])
            prefix = fact[:parameter[0]]
            report = _COUNT_REPORT.match(prefix)
            if report:
                prefix = prefix[report.end():]
            counter_noun = re.fullmatch(
                rf"\s*(?:(?:本项目|项目|当前|现有|既有)\s*)*{_SYSTEM_GROUP_NOUN}"
                rf"\s*{_COUNT_RELATION}\s*(?:为|是|共|[:：])?\s*", prefix)
            if ((tail_noun or counter_noun)
                    and _parameter_scopes_supported("一套业务系统", _parameter_scope_text(parameter, fact),
                                                    allocation=True)):
                totals.add(parameter[2][0])
    return len(totals) == 1 and next(iter(totals)) == 1 + relation["remainder_count"]


def _system_phase_scope(parameter, clause):
    """Bind a stage to an explicit counted intake/expansion, not an audit."""
    prefix = clause[:parameter[0]]
    return {_normalise(match.group()) for match in _SYSTEM_PHASE.finditer(prefix)
            if re.fullmatch(r"\s*(?:拟|计划|将)?(?:接入|扩展至)(?:另外|其余|其他|剩余)?\s*[“‘\"']?",
                            prefix[match.end():])}


def _pending(clause):
    # A suggestion alone is not evidence for a fixed numeric schedule. Conditions
    # make the scope explicit; a proposed numeric value also needs confirmation.
    # A qualifier inside a prohibited promise cannot qualify an independent
    # assertion after it (e.g. 尚未确认…承诺秒级，而固定90毫秒).
    for match in reversed(list(_PROHIBITED_PARAMETER_ACTION.finditer(clause))):
        boundary = _PROMISE_BOUNDARY.search(clause, match.end())
        clause = clause[:match.start()] + clause[boundary.start() if boundary else len(clause):]
    # A conditional trigger inside an explicitly defined rule is a committed
    # threshold, rather than a hypothetical candidate. Share this relation with
    # source extraction; other conditions and explicit pending values retain
    # their existing qualification, including an outer 若/如果 proposition.
    defined = [match.span() for match in _DEFINED_THRESHOLD_CONDITION.finditer(clause)]
    return bool(_PENDING.search(clause)
                or any(not _within_spans(match.start(), match.end(), defined)
                       for match in _CONDITION.finditer(clause))
                or (_CANDIDATE.search(clause) and _CONFIRM.search(clause)))


def _clause_pending(clauses, position, paragraph):
    clause, offset = clauses[position]
    if _pending(clause):
        return True
    if position + 1 >= len(clauses):
        return False
    following, following_offset = clauses[position + 1]
    separator = paragraph[offset + len(clause):following_offset]
    if (separator in {"，", ","}
            and any(_server_count_descriptor_scope(clause, parameter[0], parameter[1], parameter[2][1])
                    for parameter in _parameters(clause))
            and re.fullmatch(r"\s*(?:需(?:要)?|须|待)(?:确认|核实)该数量\s*", following)):
        # This explicitly qualifies the preceding count, not a later action's
        # unrelated details. Source selection uses the same local relation.
        return True
    return bool(separator in {"，", ","} and _CANDIDATE.search(clause)
                and re.match(r"\s*(?:二者|两者|这些(?:数值|参数|周期)|上述(?:数值|参数|周期)|该(?:数值|参数|周期)|均)", following)
                and _CONFIRM.search(following))


def _pending_frequency_spans(text):
    """Qualify only options inside a frequency field explicitly to be decided."""
    fields = re.compile(
        r"(?P<prefix>(?:需(?:要)?|须|待)\s*(?:明确|确认|确定)[^。！？!?；;\n]*?)"
        r"(?:检查|采集|备份|调度|同步|通知|告警|执行)?(?:频率|周期)\s*[（(]"
        r"(?P<choices>[^（）()\n]*)[）)]")
    option = r"(?:每(?:个)?(?:秒|分钟|小时|天|日|周|星期|月|季度|年)|实时|按需)"
    choices = re.compile(rf"\s*(?:如|例如)?\s*{option}(?:\s*(?:、|，|,|或者|或|及|和)\s*{option})+\s*")
    spans = [match.span("choices") for match in fields.finditer(text)
             if choices.fullmatch(match.group("choices")) and not re.search(
                 r"固定|既定|已(?:采用|配置|确定)|必须(?:按|执行)|规定(?:为|采用)|确定为",
                 match.group("prefix"))]
    missing_basis = re.compile(
        r"^\s*(?:检查|采集|备份|调度|同步|通知|告警|执行)(?:频率|周期)的具体数值\s*[（(]"
        r"(?P<choices>[^（）()\n]*)[）)]\s*缺少项目依据\s*$")
    # Only the options of this complete, explicitly ungrounded frequency field
    # are qualified. Later fixed schedules/values are still checked, and these
    # options cannot become positive source evidence for an adopted schedule.
    for clause, offset in _clauses(text):
        for match in missing_basis.finditer(clause):
            if choices.fullmatch(match.group("choices")):
                spans.append((offset + match.start("choices"), offset + match.end("choices")))
    return spans


def _qualified_parameter_spans(text):
    """Bind postposed non-assertion predicates to their own parameter mentions.

    A value list is the argument of an unset/evidence-missing predicate, rather
    than an adopted setting. Counts of people/devices and unrelated values are
    outside this grammar. Body, numeric floor and source extraction share it.
    """
    period = r"工作日|毫秒|秒|分钟|小时|天|日|周|星期|月|季度|年"
    value = rf"(?:每(?:个)?(?:{period})|(?:毫秒|秒|分钟|小时|天)级|{_NUM}\s*(?:{period}))"
    quoted = "(?:" + "|".join(re.escape(left) + value + re.escape(right)
                               for left, right in (("“", "”"), ("‘", "’"), ('"', '"'), ("'", "'"))) + ")"
    item = rf"(?:{quoted}|{value})"
    values = rf"\s*(?:如|例如)?\s*{item}(?:\s*(?:、|或|或者|及|和|与)\s*{item})*"
    unset = re.compile(
        r"\s*(?:(?:具体|该|上述)(?:的)?)?(?:延迟|响应|恢复|同步|备份|采集|调度|通知|告警)"
        r"(?:阈值|目标|指标|频率|周期|时效)\s*[（(](?P<values>" + values + r")[）)]\s*"
        + _PROHIBITED_PARAMETER_ACTION.pattern + r"\s*")
    missing = re.compile(
        r"\s*(?:任何|所有)?关于(?P<values>" + values +
        rf"(?:\s*(?:或|及|和|与)\s*具体(?:{period})数值)?)"
        r"(?:的)?(?:设定|设置|配置|承诺)(?:均|都)?(?:缺乏|缺少)项目依据\s*")
    spans = []
    for clause, offset in _clauses(text):
        for pattern in (unset, missing):
            match = pattern.fullmatch(clause)
            if match:
                spans.append((offset + match.start("values"), offset + match.end("values")))
    return spans


def _investigation_purpose_spans(text):
    """An adjacent verification purpose is not an achieved capability fact.

    Only the capability predicate is qualified; scalar parameter checks remain
    independent. A new sentence, an asserted outcome or another later action
    cannot borrow the earlier investigation's modality.
    """
    investigation = re.compile(r"\s*(?:需(?:要)?|须)(?:核实|检查|验证)[^。！？!?；;\n，,]{1,180}\s*")
    purpose = re.compile(
        r"\s*(?:以(?:便)?|从而)?(?:确保|保证)(?P<claim>[^。！？!?；;\n，,]{1,120}?"
        r"满足(?:预期|业务|设计)[^。！？!?；;\n，,]{0,24}?(?:需求|要求|目标))\s*")
    clauses = _clauses(text)
    spans = []
    for (previous, previous_offset), (clause, offset) in zip(clauses, clauses[1:]):
        separator = text[previous_offset + len(previous):offset]
        match = purpose.fullmatch(clause)
        if (separator in {"，", ","} and investigation.fullmatch(previous) and match
                and not re.search(r"已(?:经)?(?:实现|满足|保证|确保)|实测(?:表明|证明)|必然|一定|即可(?:实现|满足)",
                                  match.group("claim"))):
            spans.append((offset, offset + len(clause)))
    return spans


def _prohibited_parameter_spans(clause):
    """A forbidden setting/promise qualifies only its local parameter objects.

    This does not establish that the project has adopted a prohibition policy;
    that separate factual claim still belongs to independent full-text review.
    """
    spans = []
    for match in _PROHIBITED_PARAMETER_ACTION.finditer(clause):
        boundary = _PROMISE_BOUNDARY.search(clause, match.end())
        spans.append((match.end(), boundary.start() if boundary else len(clause)))
    return spans


def _negated_inference_spans(clause):
    """A denied inference qualifies its proposition, not other parameters."""
    spans = []
    for match in _NEGATED_INFERENCE.finditer(clause):
        boundary = _PROMISE_BOUNDARY.search(clause, match.end())
        spans.append((match.end(), boundary.start() if boundary else len(clause)))
    return spans


def _pending_conclusion_spans(text):
    """Bind an about+conclusion noun to its own complete pending predicate.

    A clipped nominal or a request to confirm another object's deadline is
    insufficient. Only the named proposition is qualified, not adjacent values.
    """
    pending = re.compile(
        rf"(?P<claim>(?:任何|所有)?关于(?:(?![。！？!?；;\n，,]|{_PROMISE_BOUNDARY.pattern}).){{1,180}}?的结论)"
        r"\s*[，,]\s*(?:均|该结论|这些结论|上述结论)\s*"
        r"(?:(?:须|需(?:要)?|必须)(?:待)?|尚待|待)\s*(?:调查|调研)?(?:确认|核实|验证)"
        rf"(?=\s*(?:[。！？!?；;\n，,]|$|{_PROMISE_BOUNDARY.pattern}))")
    return [match.span("claim") for match in pending.finditer(text)]


def _terminology_definition_spans(text):
    """Qualify quoted labels only when bound to an explicit term definition."""
    quoted = re.compile(
        r'“[^“”。！？!?；;\n，,]{1,100}”|‘[^‘’。！？!?；;\n，,]{1,100}’|'
        r'"[^"。！？!?；;\n，,]{1,100}"|\'[^\'。！？!?；;\n，,]{1,100}\'')
    definition = re.compile(
        rf"(?:统一|定义)\s*(?P<terms>(?:{quoted.pattern})(?:\s*[、，,]\s*(?:{quoted.pattern}))*)\s*"
        r"(?:(?:等|这一|这些)?(?:概念|术语|表述)(?:在(?:本项目|项目)中的)?(?:的)?(?:具体)?(?:指代|定义|含义)|"
        r"在(?:本项目|项目)中的(?:概念|术语|表述)(?:定义|含义|具体指代))")
    return [(match.start("terms") + term.start(), match.start("terms") + term.end())
            for match in definition.finditer(text) for term in quoted.finditer(match.group("terms"))]


def _metric_basis_spans(text):
    """Field names requiring evidence are not already quantified promises.

    Only lexical cadence/granularity inside a matched field list is qualified.
    A scalar value elsewhere in the same clause keeps its evidence requirement.
    """
    descriptor = (
        r"(?:毫秒|秒|分钟|小时|天)级|"
        r"每(?:个)?(?:工作日|毫秒|秒|分钟|小时|天|日|周|星期|月|季度|年)")
    field = (
        rf"(?:(?:{descriptor})(?:等)?(?:性能|响应|同步|时效|识别|检测|采集|备份|调度|检查|告警|通知|执行)?(?:指标|频率|周期)|"
        r"(?:备份|采集|同步|调度|检查|通知|告警|执行)?(?:频率|周期)|保留期|性能指标)")
    listing = re.compile(
        rf"(?P<fields>{field}(?:\s*(?:、|，|,|以及|和|及|与|或)\s*{field})*)"
        r"\s*(?:等)?(?:均|都|也)?\s*(?:须|需(?:要)?|必须|应(?:当)?)\s*"
        r"(?:对应|有|具有|具备|提供|给出)?(?:具体|可信|经确认的|本项目|项目|实测|测试|验证|业务){0,4}"
        r"(?:依据|证据)")
    spans = []
    for clause, offset in _clauses(text):
        # A trailing demand for evidence cannot qualify an actual achievement.
        if re.search(r"实际|实测表明|已(?:实现|满足|达到|保证|确定)|实现|达到|保证|确保|固定|确定为", clause):
            continue
        for match in listing.finditer(clause):
            for pattern in (_CADENCE, _GRANULARITY):
                spans.extend((offset + match.start("fields") + metric.start(),
                              offset + match.start("fields") + metric.end())
                             for metric in pattern.finditer(match.group("fields")))
    return spans


def _invalid_metric_spans(text):
    """A locally rejected metric hypothesis is not an adopted project value.

    Only cadence/granularity tokens are qualified. Count invalidations can
    contradict known inventory facts and must never share this qualification.
    """
    value = r"(?:(?:毫秒|秒|分钟|小时|天)级|每(?:个)?(?:工作日|毫秒|秒|分钟|小时|天|日|周|星期|月|季度|年))"
    field = r"(?:的)?(?:性能|响应|恢复|同步|时效|识别|检测|采集|备份|调度|检查|告警|通知|执行)?(?:指标|目标|时效|周期|频率|承诺|参数)"
    invalid = re.compile(
        rf"(?P<values>{value}(?:{field})?(?:\s*(?:、|或|或者|和|与|及)\s*{value}(?:{field})?)*)"
        r"\s*(?:均|都|一律)?\s*(?:应(?:当)?|须)?(?:视为|属于|是)"
        r"(?:无效|无依据|缺乏依据)(?:的)?(?:假设|推断|猜测|承诺)")
    spans = []
    for clause, offset in _clauses(text):
        if re.search(r"实际|实测表明|已(?:实现|满足|达到|保证)|实现|达到|保证|确保|采用|执行|配置|固定为", clause):
            continue
        for match in invalid.finditer(clause):
            for pattern in (_CADENCE, _GRANULARITY):
                spans.extend((offset + match.start("values") + metric.start(),
                              offset + match.start("values") + metric.end())
                             for metric in pattern.finditer(match.group("values")))
    return spans


def _within_spans(start, end, spans):
    return any(left <= start and end <= right for left, right in spans)


def _roles(text):
    return {key for key, pattern in _ROLE_PATTERNS.items() if pattern.search(text)}


def _server_count_descriptor_scope(clause, start, end, unit):
    """Recognise complete generic server-count descriptions in either order."""
    if unit != "台":
        return None
    pairs = {"“": "”", "‘": "’", '"': '"', "'": "'"}
    value_start, value_end = start, end
    if start and clause[start - 1] in pairs:
        if not clause[end:].startswith(pairs[clause[start - 1]]):
            return None
        value_start, value_end = start - 1, end + 1
    preceding = _SERVER_OBJECT_COUNT_PREFIX.fullmatch(clause[:value_start])
    if preceding and not clause[value_end:].strip():
        return preceding.start("noun"), value_end
    following = _SERVER_REVERSE_COUNT_SUFFIX.fullmatch(clause[value_end:])
    if (value_start != start and _COUNT_REFERENCE_PREFIX.fullmatch(clause[:value_start])
            and following and pairs.get(following.group("left"), "") == following.group("right")):
        return value_start, len(clause)
    reported = re.search(
        rf"(?P<noun>{_GENERIC_SERVER_NOUN})\s*{_COUNT_RELATION}"
        r"\s*沿用\s*(?:本项目|项目)已提供的\s*$", clause[:value_start])
    if reported and re.fullmatch(r"\s*事实\s*", clause[value_end:]):
        leading = clause[:reported.start("noun")]
        neutral = _COUNT_REFERENCE_PREFIX.fullmatch(re.sub(r"^\s*其中\s*", "", leading))
        owners = (list(_SCOPED_OBJECT.finditer(leading)) + list(_PER_OBJECT.finditer(leading))
                  + list(_UNIVERSAL_OBJECT.finditer(leading)))
        if neutral or any(re.fullmatch(r"\s*的\s*", leading[owner.end():]) for owner in owners):
            # A reported count still needs same-value/object evidence. Keep
            # bound owners, and reject unknown noun/type/procurement modifiers.
            return reported.start("noun"), len(clause)
    return None


def _quoted_generic_quantity_scope(clause, start, end, unit):
    """Paired quotes bind adjacent objects without removing a system's name.

    Server types lack a separate identity model, so only their known generic
    nouns are accepted here. Explicit system identities retain scope checks.
    """
    described = _server_count_descriptor_scope(clause, start, end, unit)
    if described:
        return described
    if unit == "台":
        noun = _GENERIC_SERVER_NOUN
    elif unit == "套":
        names = {"系统", "业务系统", "内部业务系统", "源系统", "应用系统", "数据系统", "信息系统",
                 "不同源的业务系统", "不同的业务系统"} | _NEUTRAL_BUSINESS_ALIASES
        noun = "(?:" + "|".join(sorted(names, key=lambda name: (-len(name), name))) + r"|[\u3400-\u9fffA-Za-z0-9_-]{1,24}?系统(?:[A-Za-z0-9_-]{1,16})?)"
    else:
        return None
    pairs = {"“": "”", "‘": "’", '"': '"', "'": "'"}
    quoted_noun = "(?:" + "|".join(re.escape(left) + noun + re.escape(right)
                                   for left, right in pairs.items()) + ")"
    value_start, value_end = start, end
    if start and clause[start - 1] in pairs:
        if not clause[end:].startswith(pairs[clause[start - 1]]):
            return None
        value_start, value_end = start - 1, end + 1
    before = clause[:value_start]
    relation = rf"\s*(?:{_COUNT_RELATION})?\s*(?:为|是|共|[:：])?\s*$"
    preceding = re.search(quoted_noun + relation, before)
    if preceding:
        return preceding.start(), value_end
    following = re.match(r"\s*" + quoted_noun, clause[value_end:])
    if following:
        return value_start, value_end + following.end()
    if value_start != start:
        # Quoting a count does not remove the identity of the adjacent object.
        following = re.match(r"\s*" + noun + r"(?![A-Za-z0-9_-])", clause[value_end:])
        if following:
            return value_start, value_end + following.end()
        preceding = re.search(r"(?<![\u3400-\u9fffA-Za-z0-9_-])" + noun + relation, before)
        if preceding:
            return preceding.start(), value_end
    return None


def _server_counter_prefix(text):
    match = _SERVER_COUNT_PREFIX.search(text)
    if (match and match.group("total") and match.start() and text[match.start() - 1] == "的"
            and not match.group("total").startswith(("本项目", "项目"))
            and not _count_owner_prefix(text[:match.start()])):
        # 认证的服务器 is a role modifier; 财务系统的服务器 has an owner.
        return False
    return bool(match)


def _parameters(clause):
    found = []
    for pattern, kind in ((_QUANTITY, "quantity"), (_CADENCE, "cadence"),
                          (_GRANULARITY, "granularity"), (_PERCENT, "percent"),
                          (_EXPLICIT_NUMBER, "setting"), (_BARE_SETTING, "bare_setting")):
        for match in pattern.finditer(clause):
            if any(match.start() >= start and match.end() <= end for start, end, *_ in found):
                continue
            if kind == "bare_setting" and any(
                    start <= match.start("number") and match.end("number") <= end
                    for start, end, *_ in found):
                continue
            raw = match.groupdict()
            tail = clause[match.end():]
            unit_text = raw.get("unit", "")
            quoted_scope = (_quoted_generic_quantity_scope(clause, match.start(), match.end(), unit_text)
                            if kind == "quantity" else None)
            if (kind == "quantity" and raw.get("number") == "一" and (
                    (unit_text == "人" and clause[:match.start()].endswith(("唯", "任"))
                     and tail.startswith("员"))
                    or (unit_text == "台" and clause[:match.start()].endswith("唯")
                        and tail.startswith("账")))):
                # 唯一/任一 + 人员 and 唯一 + 台账 contain lexical 一, not
                # person/device quotas. Only this match is removed, in both
                # authored text and evidence; later actual counts remain.
                continue
            if (kind == "quantity" and raw.get("number") == "一" and unit_text == "人"
                    and clause[:match.start()].endswith("这")
                    and tail.startswith("工") and not tail.startswith("工作")):
                # 这一 + 人工 is a demonstrative and lexical word, not one
                # person. 这一人工作… and other actual person counts remain.
                continue
            if (kind == "quantity" and raw.get("number") == "一"
                    and unit_text in {"台", "套", "个", "项", "节点", "条"}
                    and clause[:match.start()].endswith("每")):
                # 每一条核查结论 enumerates the objects being checked. It does
                # not qualify another value, such as 每一条记录8GB or 保留90天.
                continue
            if (kind == "quantity" and raw.get("number") == "一"
                    and clause[:match.start()].endswith("任意")
                    and ((unit_text == "条" and tail.startswith("记录"))
                         or (unit_text == "次" and re.match(
                             r"(?:失败)?(?:重试|重复执行|轮询)(?:均|都)", tail)))):
                # 任意一条记录/任意一次重试均… quantify over all instances,
                # rather than fixing a record/retry quota. Skip this token in
                # body and source; a capacity or later actual quota is separate.
                continue
            if (kind == "quantity" and raw.get("number") == "一" and unit_text == "条"
                    and re.search(r"补充\s*$", clause[:match.start()])
                    and re.match(r"(?:约束)?(?:验证|论证)路径(?=\s*(?:[:：。！？!?；;，,]|$))", tail)):
                # This classifier counts an explanatory method under a writing
                # action, not records or a project resource/retention quota.
                continue
            if (kind == "quantity" and unit_text in {"个", "项"}
                    and not re.match(r"\s*(?:物理)?(?:节点|服务器|主机|磁盘|用户|账户|账号|许可证|设备|机房|连接|线程|副本|(?:典型)?冲突案例)", tail)):
                continue
            if (kind == "quantity" and unit_text == "套"
                    and not quoted_scope
                    and not re.search(r"系统|设备|硬件|软件|服务器", tail[:15])
                    and not re.search(rf"(?:{_COUNTED_SYSTEM_NOUN}|设备|硬件|软件|服务器)(?:{_COUNT_RELATION})?\s*(?:为|是|共|[:：])?\s*$",
                                      clause[max(0, match.start() - 22):match.start()])):
                continue
            if (kind == "quantity" and unit_text == "次" and (
                    _number(raw["number"]) in {1, 2}
                    or clause[max(0, match.start() - 2):match.start()].endswith("每"))):
                # 一次性、逐次访问、恰好一次语义及二次复核是概念或检查步骤。
                # Actual retry/polling counts require evidence whether the
                # action appears before or after the number. A review of the
                # retry policy is still an abstract confirmation process.
                local_action = clause[max(0, match.start() - 22):match.end() + 22]
                concept = (tail.startswith("性") or clause[:match.start()].endswith("恰好")
                           or (_number(raw["number"]) == 1 and clause[:match.start()].endswith("每"))
                           or re.match(r"\s*(?:确认|复核|核实|验证|检查)", tail))
                if concept or not re.search(r"重试|重复执行|轮询", local_action):
                    continue
            if (kind == "cadence" and re.match(r"(?:查询率|请求率|请求数|吞吐|入库行数|数据增长率|增量大小|增量行数|增量(?:数据)?速率)", tail)):
                continue
            number = _number(raw.get("number") or "1")
            unit = _unit(raw.get("unit") or ("%" if kind == "percent" else "setting"))
            if kind == "bare_setting":
                # A unitless count belongs to its named parameter, never to a
                # server count or another setting sharing the same numeral.
                name = re.sub(r"^(?:本项目|项目|当前|目前|现有|既有)", "", raw["name"])
                unit = "setting:" + name.casefold()
            local = clause[max(0, match.start() - 22):match.end() + 22]
            roles = _roles(local)
            system_counter = re.search(
                rf"{_COUNTED_SYSTEM_NOUN}(?:{_COUNT_RELATION})?\s*(?:为|是|共|[:：])?\s*$", clause[:match.start()])
            if kind == "quantity" and unit_text == "套" and (
                    quoted_scope or system_counter or "business_system" in _roles(clause)):
                roles = {"business_system"}
            else:
                # A business system can be the container of a backup/retention
                # parameter without changing that parameter's semantic role.
                roles.discard("business_system")
            if kind == "quantity" and unit_text == "台":
                # A nearby server cannot justify the count of a different device.
                before = clause[:match.start()]
                server_object = (re.match(r"\s*(?:(?:现有|既有|数据)\s*)*(?:服务器|主机)", tail)
                                 or _server_counter_prefix(before)
                                 or re.match(r"(?:提供服务|配置为(?:备用|主)节点|作为(?:临时)?(?:主控|备用|缓冲)节点)", tail))
                roles = {"server"} if server_object or quoted_scope else roles - {"server"}
            found.append((match.start(), match.end(), (number, unit, kind), roles, match.group()))
    return sorted(found, key=lambda item: item[0])


def _negative_quoted_quantity_evidence(clause):
    for parameter in _parameters(clause):
        scope = _quoted_generic_quantity_scope(clause, parameter[0], parameter[1], parameter[2][1])
        if scope and re.search(r"(?:没有|不存在|无)\s*(?:(?:配置|部署|拥有|安装|运行)\s*)?$", clause[:scope[0]]):
            return True
    return False


def _trusted_text(value):
    """Do not flatten IDs, metadata, instructions or public reference sections."""
    if isinstance(value, str):
        # Bare uploaded-document titles/IDs also belong to company evidence.
        # Only explicitly attributed public-reference blocks are excluded.
        blocks = _DOCUMENT_HEADER.split(value)
        return "\n".join(block for block in blocks if not (
            re.search(r"来源机构\s*[:：]", block)
            and re.search(r"(?:精确URL|来源URL|https?://)", block)
            and re.search(r"通用参考|非本项目事实|公开(?:技术)?资料|用途声明", block)))
    if isinstance(value, (list, tuple)):
        return "\n".join(_trusted_text(part) for part in value)
    if not isinstance(value, Mapping):
        return ""
    if value.get("kind") in {"public", "reference", "public_reference"} or value.get("is_public") is True:
        return ""
    parts = [_trusted_text(value[key]) for key in
             ("project", "background", "conditions", "statements", "facts", "project_facts", "text", "content") if key in value]
    for item in value.get("items", []):
        if isinstance(item, Mapping):
            parts.append(f"{item.get('name', '')}数量：{item.get('quantity', '')}{item.get('unit', '')}")
    return "\n".join(parts)


def project_fact_text(project_facts):
    """Public provenance-preserving extraction for worker checks and prompts."""
    return _trusted_text(project_facts)


def _public_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return "\n".join(_public_text(part) for part in value)
    if isinstance(value, Mapping):
        return "\n".join(_public_text(value[key]) for key in
                         ("text", "content", "background", "title", "original_name") if key in value)
    return ""


def _reference_identity(value):
    value = re.sub(r"官方|文档|版本|框架|自|[（）()\s]", "", value).casefold()
    return value.replace("apache", "").replace("–", "-").replace("—", "-")


def _software_version_mentions(text):
    """Return local software/component + version identities, never bare digits.

    An uploaded document title can identify its component in a later framework
    version statement. In ordinary prose a directly adjacent named subject is
    required; Connect needs Kafka attribution in the same local context.
    """
    software = re.compile(
        r"(?<![A-Za-z0-9_])(?:PostgreSQL|(?:Apache\s+)?Kafka(?:\s+Connect)?|"
        r"Great\s+Expectations|Prometheus|Connect)(?![A-Za-z0-9_])", re.I)
    version = re.compile(r"自\s*(?P<version>\d+(?:\.\d+){1,3})\s*(?:版本)?\s*起(?![A-Za-z0-9_.])")

    def family(name, context):
        name = re.sub(r"\s+", "", name).casefold().replace("apache", "")
        if name == "connect":
            return "kafkaconnect" if re.search(r"(?<![A-Za-z0-9_])Kafka(?![A-Za-z0-9_])", context, re.I) else None
        return name

    found = []
    block_offset = 0
    for block in _DOCUMENT_HEADER.split(text):
        title = re.match(r"\s*标题\s*[:：]([^\n]*)", block)
        title_names = list(software.finditer(title.group(1))) if title else []
        inherited = family(title_names[-1].group(), title.group(1)) if title_names else None
        for clause, offset in _clauses(block):
            if _pending(clause) or _NEGATED_EVIDENCE.search(clause) or _NEGATED_INFERENCE.search(clause):
                continue
            for match in version.finditer(clause):
                prefix = clause[:match.start()]
                names = list(software.finditer(prefix))
                name = names[-1] if names else None
                identity = None
                if name and re.fullmatch(r"\s*(?:框架|软件|组件)?(?:支持)?\s*", prefix[name.end():]):
                    identity = family(name.group(), prefix[max(0, name.start() - 80):] + (title.group(1) if title else ""))
                elif inherited and re.search(r"(?:源连接器(?:框架)?|框架|软件|组件)(?:支持)?\s*$", prefix):
                    identity = inherited
                if (identity and not (_PROJECT.search(prefix) and not title
                                      and not re.search(r"文档|指南|规范|来源|参考资料", prefix))):
                    found.append((identity, match.group("version"),
                                  block_offset + offset + match.start("version"),
                                  block_offset + offset + match.end("version")))
        block_offset += len(block)
    return found


def unsupported_numeric_claims(paragraphs, *, project_facts=None, source_context=None):
    """Keep the numeric floor aligned with locally grounded/qualified parameters.

    A public standard/version identifier is not a project parameter. Its digits
    never become a global whitelist: the same value used as a port, retention
    period or capacity elsewhere in a sentence still requires project evidence.
    Subject/purpose checks for grounded quantities remain in inspect_content_quality.
    """
    evidence = _evidence(project_fact_text(project_facts))
    reference_ids = {_reference_identity(match.group())
                     for match in _REFERENCE_IDENTIFIERS.finditer(_public_text(source_context))}
    reference_versions = {(software, version) for software, version, *_
                          in _software_version_mentions(_public_text(source_context))}
    issues = []
    for index, paragraph in enumerate(paragraphs):
        spans = [match.span() for match in _REFERENCE_IDENTIFIERS.finditer(paragraph)
                 if _reference_identity(match.group()) in reference_ids]
        spans.extend(match.span() for match in _LEXICAL_NUMERIC_IDENTIFIERS.finditer(paragraph))
        spans.extend((start, end) for software, version, start, end in _software_version_mentions(paragraph)
                     if (software, version) in reference_versions)
        spans.extend(match.span() for match in re.finditer(r"(?m)^\s*\d{1,3}[.、)）]\s+(?=\S)", paragraph))
        spans.extend(match.span() for match in re.finditer(
            r"\d{1,3}(?:个(?:评估|分析|检查)维度|种(?:校验|检查|分析)规则|项(?:检查|分析|评估)步骤)", paragraph))
        clauses = _clauses(paragraph)
        remainders = _conditional_system_remainders(paragraph)
        pending_fields = _pending_frequency_spans(paragraph)
        basis_fields = _metric_basis_spans(paragraph) + _invalid_metric_spans(paragraph) + _qualified_parameter_spans(paragraph)
        for position, (clause, offset) in enumerate(clauses):
            prohibited = _prohibited_parameter_spans(clause)
            for parameter in _parameters(clause):
                remainder = remainders.get((offset + parameter[0], offset + parameter[1]))
                if remainder:
                    if _conditional_remainder_supported(remainder, evidence):
                        spans.append((offset + parameter[0], offset + parameter[1]))
                    continue
                if (_clause_pending(clauses, position, paragraph)
                        or _within_spans(parameter[0], parameter[1], prohibited)
                        or _within_spans(offset + parameter[0], offset + parameter[1], pending_fields)
                        or _within_spans(offset + parameter[0], offset + parameter[1], basis_fields)
                        or _parameter_supported(parameter, clause, evidence)):
                    spans.append((offset + parameter[0], offset + parameter[1]))
            # Bare source values outside the recognised parameter forms need
            # literal local assertion support, rather than a numeric whitelist.
            if not any(r["consequence_offset"] == offset for r in remainders.values()) and any(
                   _parameter_scopes_supported(clause, fact, allocation=True)
                   and _normalise(clause) in _normalise(fact)
                   for fact, _ in evidence):
                spans.extend((offset + match.start(), offset + match.end())
                             for match in re.finditer(r"\d+(?:\.\d+)?", clause))
        for match in re.finditer(r"\d+(?:\.\d+)?", paragraph):
            if any(start <= match.start() and match.end() <= end for start, end in spans):
                continue
            issues.append({"code": "unsupported_number", "paragraph_index": index,
                           "parameter": match.group(), "claim": paragraph[max(0, match.start() - 70):match.end() + 70],
                           "correction": "该正文数字缺少项目依据，且不是来源中可核验的标准或软件版本标识；移除无依据参数或补充经确认的项目资料。"})
    return issues


def _evidence(text):
    # A discussed conclusion or quoted term definition cannot authorise its
    # underlying diagnosis. Preserve unrelated positive facts and offsets.
    qualified = _pending_conclusion_spans(text) + _terminology_definition_spans(text) + _investigation_purpose_spans(text)
    for start, end in sorted(qualified, reverse=True):
        text = text[:start] + " " * (end - start) + text[end:]
    pending_fields = _pending_frequency_spans(text)
    basis_fields = _metric_basis_spans(text) + _invalid_metric_spans(text) + _qualified_parameter_spans(text)
    clauses = _clauses(text)
    conditional_offsets = {relation["consequence_offset"]
                           for relation in _conditional_system_remainders(text).values()}
    return [(clause, [parameter for parameter in _parameters(clause)
                      if not _within_spans(offset + parameter[0], offset + parameter[1], pending_fields)
                      and not _within_spans(offset + parameter[0], offset + parameter[1], basis_fields)])
            for position, (clause, offset) in enumerate(clauses)
            if offset not in conditional_offsets and not _pending(clause) and not _NEGATED_EVIDENCE.search(clause)
            and not (_SYSTEM_PHASE.search(clause) and _NEGATED_SYSTEM_PHASE_ALLOCATION.search(clause))
            and not _NEGATED_STANDARD_DEFICIT.search(clause)
            and not _NEGATED_COUNT_ADDITION.search(clause)
            and not _NEGATED_INFERENCE.search(clause)
            and not _negative_quoted_quantity_evidence(clause)
            and not (any(_server_count_descriptor_scope(clause, p[0], p[1], p[2][1])
                         for p in _parameters(clause))
                     and _clause_pending(clauses, position, text))
            and not _PROHIBITED_PARAMETER_ACTION.search(clause)]


def _normalise(text):
    text = re.sub(r"\s+|[：:、()（）]", "", text)
    return re.sub(_NUM, lambda match: str(_number(match.group())), text)


def _parameter_object_scopes(text):
    """Keep explicitly named systems/departments separate from generic scope."""
    generic = {"系统", "业务系统", "内部业务系统", "应用系统", "数据系统", "信息系统",
               "不同源的业务系统", "不同的业务系统", "源系统",
               "数据库", "部门", "业务部门", "本系统", "该系统", "这些系统", "上述系统"}
    # These complete generic phrases do not name a new counted system. The
    # adjective's deployment meaning still requires separate full-text review.
    # Never strip arbitrary modifiers: 独立的财务系统 and 源系统A stay named.
    generic |= _NEUTRAL_BUSINESS_ALIASES
    named, universal = {}, set()
    for match in _UNIVERSAL_OBJECT.finditer(text):
        universal.add("数据库" if match.group().endswith("数据库") else
                      "部门" if match.group().endswith("部门") else "系统")
    for match in _SCOPED_OBJECT.finditer(text):
        label = match.group()
        # A local number/classifier marks the noun phrase's left boundary.
        # Prose such as “由于缺乏三套业务系统” is not a new system name;
        # “结合三套星云档案系统” still retains the explicit 星云档案 identity.
        quantities = list(re.finditer(rf"{_NUM}\s*(?:套|个)\s*", label))
        if quantities:
            label = label[quantities[-1].end():]
        pairs = {"“": "”", "‘": "’", '"': '"', "'": "'"}
        quoted_noun = bool(match.start() and text[match.start() - 1] in pairs
                           and text[match.end():].startswith(pairs[text[match.start() - 1]]))
        counter_noun = bool(re.match(
            rf"\s*{_COUNT_RELATION}\s*(?:为|是|共|[:：])?\s*{_NUM}\s*(?:套|台|个)", text[match.end():]))
        # Once the count binds a complete noun, embedded verbs are part of its
        # identity: 资料确认系统 is not an instruction to confirm a generic 系统.
        if not (quantities or quoted_noun or counter_noun):
            label = re.sub(r"^.*(?:针对|对接|连接|部署|采用|使用|沿用|确认|核实|覆盖|采集自|来自|统一|整合|汇聚|接入|纳入|包括|涉及|面向|支持)", "", label)
        label = re.sub(r"^(?:(?:本项目|项目|当前|目前|现有|既有|公司|其中|上述|所有|全部|各个|各套|每个|每套|各|在|对|的|和|及|中|将|由|从|为|拟)|[零〇一二两三四五六七八九十百\d]+套)+", "", label)
        label = re.sub(rf"^每(?={_ALLOCATION_OBJECT}$)", "", label)
        if label in generic:
            continue
        suffix = re.search(r"数据库|部门|系统", label)
        if suffix:
            named.setdefault(suffix.group(), set()).add(label.casefold())
    return named, universal


def _parameter_allocation_scopes(text):
    def kind(label):
        return "数据库" if label.endswith("数据库") else "部门" if label.endswith("部门") else "系统"

    per_object = {kind(match.group()) for match in _PER_OBJECT.finditer(text)}
    if _ELIDED_PER_OBJECT.search(text):
        per_object.add("未明确对象")
    collective = set()
    for match in _COLLECTIVE_OBJECT.finditer(text):
        object_match = re.search(_ALLOCATION_OBJECT, match.group())
        collective.add(kind(object_match.group()))
    return per_object, collective


def _parameter_scopes_supported(clause, fact, *, allocation=False):
    claims, _ = _parameter_object_scopes(clause)
    sources, universal = _parameter_object_scopes(fact)
    if allocation:
        claim_per, _ = _parameter_allocation_scopes(clause)
        source_per, source_collective = _parameter_allocation_scopes(fact)
        # A total cannot establish an allocation to every object. Conversely,
        # each-object evidence supports that object or a named member, not a sum.
        if claim_per - source_per:
            return False
        if any(not claims.get(kind) for kind in source_per - claim_per):
            return False
        if any(kind in claim_per or claims.get(kind) for kind in source_collective):
            return False
        universal |= source_per
    for kind in claims.keys() | sources.keys():
        if kind in universal:
            continue
        # A specific source does not establish an unscoped/project-wide claim;
        # an unscoped fact does not establish a new named system's parameter.
        if not claims.get(kind) or not claims[kind] <= sources.get(kind, set()):
            return False
    return True


def _count_argument_prefix(prefix):
    """Exclude completed sibling argument contents from the active argument.

    Keep current and ancestor scopes, plus labels outside the parentheses.
    Only balanced sibling nodes linked by an enumeration delimiter qualify.
    """
    stack, completed = [], []
    closing = {")": "(", "）": "（"}
    for position, char in enumerate(prefix):
        if char in {"(", "（"}:
            stack.append((position, char, stack[-1][0] if stack else None))
        elif char in closing:
            if not stack or stack[-1][1] != closing[char]:
                return prefix
            start, _, parent = stack.pop()
            completed.append((start, position, parent))
    if not stack:
        return prefix
    active, _, parent = stack[-1]
    cursor, masked = active, list(prefix)
    siblings = sorted((node for node in completed if node[2] == parent and node[1] < active),
                      key=lambda node: node[1], reverse=True)
    for start, end, _ in siblings:
        if not re.fullmatch(r"\s*、[^（）()]*", prefix[end + 1:cursor]):
            break
        masked[start + 1:end] = " " * (end - start - 1)
        cursor = start
    return "".join(masked)


def _count_owner_prefix(prefix):
    """Retain only objects directly owning/configuring the counted noun.

    An actor in 向X索取/请X核对 is outside this relation regardless of its
    name. Adjacent owners, each-object allocations and collective totals keep
    their existing identity checks. Unrecognised ownership stays conservative.
    """
    # Recognise the recipient + request relation, not a list of actor names.
    # Preserve any subject before it and any actual owner after the request.
    def request_scope(match):
        # A quantified recipient is ambiguous with allocation to every member.
        # Keep its complete scope rather than turning it into a project total.
        allocations = list(_PER_OBJECT.finditer(match.group())) + list(_UNIVERSAL_OBJECT.finditer(match.group()))
        if allocations:
            return match.group()[min(item.start() for item in allocations):]
        return ""

    prefix = _count_argument_prefix(prefix)
    prefix = re.sub(r"(?:向|请|要求)[^。！？!?；;\n，,]*?(?:索取|收集|核对)\s*", request_scope, prefix)
    relation = re.compile(
        r"\s*(?:的|有|拥有|配置|部署|配备|分配|共用|共有|合计|总计|总共|"
        r"共(?:有|用|享|同|配置|部署)?)?(?:了)?\s*$")
    objects = list(_SCOPED_OBJECT.finditer(prefix))
    # Complete allocation phrases have a clearer left boundary than a broad
    # named-object match that may also contain the preceding request predicate.
    candidates = objects + list(_PER_OBJECT.finditer(prefix)) + list(_UNIVERSAL_OBJECT.finditer(prefix))
    bound = [match for match in candidates if relation.fullmatch(prefix[match.end():])]
    if not bound:
        return prefix if objects or _ELIDED_PER_OBJECT.search(prefix) else ""
    owner = max(bound, key=lambda match: (match.end(), match.start()))
    start = owner.start()
    # Multiple adjacent owners remain one bound group: 财务系统和人事系统.
    for previous in reversed(objects):
        if previous.end() > start:
            continue
        gap = prefix[previous.end():start]
        if (re.fullmatch(r"\s*(?:和|与|及|以及|、)\s*", gap)
                or (not gap and re.match(r"(?:和|与|及|以及)", prefix[start:]))):
            start = previous.start()
        else:
            break
    return prefix[start:]


def _parameter_scope_text(parameter, clause):
    """Bind a count to its noun and explicit owner, excluding request actors.

    财务系统的两台服务器 remains owned by 财务系统. A requested three-system
    inventory does not belong to the department receiving the request. Unknown
    noun/owner boundaries keep the original conservative scope.
    """
    start, end, value, roles, _ = parameter
    report = _COUNT_REPORT.match(clause[:start])
    counted_assertion = clause[report.end():end] if report else clause[:end]
    quoted_scope = _quoted_generic_quantity_scope(clause, start, end, value[1])
    if quoted_scope:
        return _count_owner_prefix(clause[:quoted_scope[0]]) + clause[quoted_scope[0]:quoted_scope[1]]
    if value[1:] == ("台", "quantity"):
        following = re.match(r"\s*(?:(?:现有|既有|数据)\s*)*(?:服务器|主机)", clause[end:])
        if following:
            return _count_owner_prefix(clause[:start]) + clause[start:end + following.end()]
        if _server_counter_prefix(clause[:start]):
            return counted_assertion
    if value[1:] == ("套", "quantity") and roles == {"business_system"}:
        project_noun = re.search(
            rf"(?<![\u3400-\u9fffA-Za-z0-9_-])(?:本项目|项目)拟整合的"
            rf"(?P<noun>(?:内部)?业务系统)\s*{_COUNT_RELATION}"
            r"\s*(?:为|是|共|[:：])?\s*$", clause[:start])
        if project_noun:
            # The explicit project relation modifies a generic counted noun,
            # not its identity. Preserve any actual owner/allocation before it.
            return _count_owner_prefix(clause[:project_noun.start()]) + clause[project_noun.start("noun"):end]
        following = re.match(r"\s*[\u3400-\u9fffA-Za-z0-9_-]{0,24}?系统(?:[A-Za-z0-9_-]{1,16})?", clause[end:])
        if following:
            return _count_owner_prefix(clause[:start]) + clause[start:end + following.end()]
        if re.search(rf"{_COUNTED_SYSTEM_NOUN}(?:{_COUNT_RELATION})?\s*(?:为|是|共|[:：])?\s*$", clause[:start]):
            return counted_assertion
    return clause


def _parameter_supported(parameter, clause, evidence):
    _, _, value, roles, claim = parameter
    for fact, parameters in evidence:
        for candidate in parameters:
            if (value[1:] == ("套", "quantity") and roles == {"business_system"}
                    and _system_phase_scope(parameter, clause) != _system_phase_scope(candidate, fact)):
                # A project inventory does not approve a phase allocation;
                # an explicitly approved phase count stays within that phase.
                continue
            if (value[1:] == ("台", "quantity")
                    and (_server_count_descriptor_scope(clause, parameter[0], parameter[1], value[1])
                         or _server_count_descriptor_scope(fact, candidate[0], candidate[1], candidate[2][1]))
                    and roles != candidate[3]):
                # A new generic count descriptor cannot be authorized by a
                # literal substring inside an unrecognised typed-server noun.
                continue
            if (value[2] == "quantity" and value[1] in {"台", "套"}
                    and bool(_COUNT_ADDITION.search(clause[:parameter[1]]))
                    != bool(_COUNT_ADDITION.search(fact[:candidate[1]]))):
                # Existing totals and additions are different uses of a count.
                # A quoted noun or 总数 must not turn either into the other.
                continue
            if not _parameter_scopes_supported(_parameter_scope_text(parameter, clause),
                                               _parameter_scope_text(candidate, fact),
                                               allocation=value[2] == "quantity" and value[1] in {"台", "套", "节点", "个", "项", "人"}):
                continue
            if roles & {"cost", "retention", "sampling"}:
                object_patterns = (r"审计(?:日志|记录|数据)", r"业务数据", r"交易(?:数据|记录)|订单数据",
                                   r"硬件", r"软件")
                objects = {index for index, pattern in enumerate(object_patterns) if re.search(pattern, clause)}
                evidence_objects = {index for index, pattern in enumerate(object_patterns) if re.search(pattern, fact)}
                if (evidence_objects or ("cost" in roles and objects)) and objects != evidence_objects:
                    continue
            if value != candidate[2]:
                # Cadence and quantity have distinct meanings: 每日 != 一天.
                if (value[1:] == candidate[2][1:] and value[0] == 1
                        and candidate[2][0] >= 2 and roles == {"server"}
                        and candidate[3] == {"server"}
                        and not re.search(r"新增|新购|采购|购置|扩容|补充|增购", clause)
                        and re.search(r"其中|另一|(?:现有|既有).{0,12}中的|切换后.{0,12}仅剩|(?:配置为|作为).{0,8}(?:主节点|备用节点|备节点|缓冲节点)", clause)):
                    return True
                continue
            if value[2] == "bare_setting":
                return True
            evidence_roles = candidate[3]
            if roles and roles == evidence_roles:
                return True
            if not roles and not evidence_roles:
                # Structured item evidence is emitted as 名称数量：量值单位.
                # Match the same explicit name, not a bag of numeric values.
                prefix = fact[:candidate[0]].strip()
                if re.search(r"数量\s*[:：]\s*$", prefix):
                    name = re.sub(r"数量\s*[:：]\s*$", "", prefix).strip()
                    before, after = clause[:parameter[0]].rstrip(), clause[parameter[1]:].lstrip()
                    if len(name) >= 2 and (after.startswith(name) or before.endswith(name)):
                        return True
            if _normalise(clause) in _normalise(fact) or _normalise(fact) in _normalise(clause):
                return True
            # Accept object synonyms without allowing a parameter shared by
            # unrelated uses (one hour of data loss versus one hour of recovery).
            if roles in ({"server"}, {"business_system"}) and roles == evidence_roles:
                return True
    return False


def _status_supported(clause, marker, evidence):
    assertions = [_normalise(clause)]
    problem = _STANDARD_PROBLEM_STATUS.fullmatch(clause)
    if problem and marker in {"缺乏统一标准", "缺乏统一的标准"}:
        # Necessity prose refers to the enclosed state, whose complete object,
        # count and stages still need literal trusted evidence. No other claim
        # or parameter is qualified by this local comparison.
        assertions.append(_normalise(problem.group("proposition")))
    for fact, _ in evidence:
        if any(assertion in _normalise(fact) for assertion in assertions):
            return True
    return False


def inspect_content_quality(paragraphs, *, project_facts=None, source_context=None, chapter_ids=()):
    """Return deterministic issues with zero-based paragraph indices.

    ``paragraphs`` is a sequence of strings or mappings containing ``text``.
    Other mapping fields (including source_ids, id, title) are never body text.
    ``project_facts`` may be trusted text, a list or a model_input-style mapping;
    the caller is responsible for source provenance before merging attachments.
    ``source_context`` can only support explicitly attributed reference claims.
    No success flag is returned: an empty result is not complete fact review.
    """
    if isinstance(paragraphs, (str, Mapping)):
        paragraphs = [paragraphs]
    facts = _evidence(_trusted_text(project_facts))
    references = _evidence(_public_text(source_context))
    identifiers = tuple(str(value) for value in chapter_ids if value)
    issues = []

    def add(code, index, paragraph, claim, correction, *, parameter=None):
        issue = {"code": code, "paragraph_index": index, "paragraph": paragraph,
                 "claim": claim, "correction": correction}
        if parameter is not None:
            issue["parameter"] = parameter
        if not any(prior["code"] == code and prior["paragraph_index"] == index
                   and prior["claim"] == claim and prior.get("parameter") == parameter for prior in issues):
            issues.append(issue)

    for index, paragraph in enumerate(paragraphs or []):
        paragraph = paragraph.get("text", "") if isinstance(paragraph, Mapping) else paragraph
        if not isinstance(paragraph, str):
            continue
        for claim, correction in _technical_concept_mismatches(paragraph, source_context):
            add("technical_concept_mismatch", index, paragraph, claim, correction)
        for match in (*_UUID.finditer(paragraph), *_CHAPTER_ID.finditer(paragraph)):
            add("body_source_identifier", index, paragraph, match.group(),
                "删除正文中的来源UUID或内部章节ID；引用改用来源机构与文档名称，ID仅放元数据。")
        for identifier in identifiers:
            if identifier in paragraph:
                add("body_source_identifier", index, paragraph, identifier,
                    "删除正文内部章节标识，改用人工确认的章节名称。")
        clauses = _clauses(paragraph)
        remainders = _conditional_system_remainders(paragraph)
        pending_fields = _pending_frequency_spans(paragraph)
        basis_fields = _metric_basis_spans(paragraph) + _invalid_metric_spans(paragraph) + _qualified_parameter_spans(paragraph)
        pending_conclusions = _pending_conclusion_spans(paragraph)
        defined_terms = _terminology_definition_spans(paragraph)
        purposes = _investigation_purpose_spans(paragraph)
        for position, (clause, offset) in enumerate(clauses):
            if _clause_pending(clauses, position, paragraph):
                continue
            if (_RECOVERY_OBJECTIVE_MIXUP.search(clause)
                    and not re.search(r"不能|不应|不得|错误|误称|不准确|混淆", clause)):
                add("technical_concept_mismatch", index, paragraph, clause.strip(),
                    "区分恢复时间目标（RTO）与恢复点目标（RPO）；两者分别描述恢复时长与数据恢复点，不能合称恢复时间目标。")
            attributed = bool(re.search(r"文档|指南|规范|标准|来源|参考资料", clause)) and not bool(
                re.search(r"本项目|现有|既有|已选型|已部署|已满足", clause))
            prohibited = _prohibited_parameter_spans(clause)
            for parameter in _parameters(clause):
                remainder = remainders.get((offset + parameter[0], offset + parameter[1]))
                if (_within_spans(offset + parameter[0], offset + parameter[1], pending_fields)
                        or _within_spans(offset + parameter[0], offset + parameter[1], basis_fields)
                        or _within_spans(parameter[0], parameter[1], prohibited)):
                    continue
                if (_conditional_remainder_supported(remainder, facts) if remainder
                        else _parameter_supported(parameter, clause, facts)):
                    continue
                if not remainder and attributed and _parameter_supported(parameter, clause, references):
                    continue
                add("unsupported_parameter", index, paragraph, clause.strip(),
                    f"具体参数“{parameter[4]}”缺少同一对象与用途的项目依据；在该断言中写待确认，"
                    "或明确可核验的条件候选及确认要求；不要用通用免责声明或其他来源的同值数字代替依据。",
                    parameter=parameter[4])
            inferences = _negated_inference_spans(clause)
            qualified_status = inferences + [(start - offset, end - offset)
                                             for start, end in pending_conclusions + defined_terms]
            qualified_status += [match.span() for match in _NEGATED_STANDARD_DEFICIT.finditer(clause)]
            deficit = next((match for match in _DEFICITS.finditer(clause)
                            if not _within_spans(match.start(), match.end(), qualified_status)), None)
            if deficit and _PROJECT.search(clause) and not _status_supported(clause, deficit.group(), facts):
                if not re.search(r"可能|或许|待调研|需核实", clause):
                    add("unsupported_project_status", index, paragraph, clause.strip(),
                        "该既有现状诊断没有可信项目事实支持；改为具体待核实事项或若存在该问题的条件场景。"
                        "建设目标和公开参考不能证明现有能力缺失。")
            # A joined affirmative assertion may omit the project/device subject
            # from the preceding assessment limit; it still needs evidence.
            scope_clause = clause
            if position:
                previous, previous_offset = clauses[position - 1]
                separator = paragraph[previous_offset + len(previous):offset]
                if (not re.search(r"[。！？!?；;\n]", separator)
                        and not re.search(r"文档|指南|规范|标准|来源|参考资料", previous)):
                    scope_clause = previous + clause
            device_premise = any(parameter[2][1] in {"台", "节点"} for parameter in _parameters(scope_clause))
            qualified_capability = qualified_status + [(start - offset, end - offset) for start, end in purposes]
            if (any(not _within_spans(match.start(), match.end(), qualified_capability)
                    for match in _CAPABILITY.finditer(clause)) and _CERTAINTY.search(clause)
                    and (_PROJECT.search(scope_clause) or (device_premise and not attributed))
                    and not (re.search(r"设计目标|建设目标|目标是|要求|需支持|应支持|旨在", clause)
                             and not re.search(r"已实现|已满足|已保证|实测表明|即可实现|"
                                               r"(?:无法|不能)(?:实现|达到|满足|保证|维持|支撑|提供)", clause))
                    and not _EPISTEMIC.search(clause) and not any(
                        _normalise(clause) in _normalise(fact) for fact, _ in facts)):
                add("unsupported_capability_claim", index, paragraph, clause.strip(),
                    "不能从设备数量或公开技术文档推出本项目仲裁、性能或可靠性结论；"
                    "明确依赖拓扑、配置、故障模型与验证结果，并将结论写为待验证的条件判断。")
    return issues


def _body_text(value):
    return value.get("text", "") if isinstance(value, Mapping) else value


def _duplicate_normalise(text):
    text = re.sub(r"\s+", "", text)
    # Only a leading outline marker is ignored, not meaningful project values.
    return re.sub(rf"^(?:第{_NUM}[章节]|[（(]?{_NUM}[）)、.．]|[一二三四五六七八九十]+、)", "", text)


def _shared_long_span(left, right):
    """Return an exact contiguous copy, using a linear-size substring index."""
    required = max(180, (min(len(left), len(right)) * 35 + 99) // 100)
    # A suffix automaton avoids quadratic diffs for repetitive long prose.
    transitions, lengths, links = [{}], [0], [-1]
    last = 0
    for char in left:
        current = len(lengths)
        transitions.append({})
        lengths.append(lengths[last] + 1)
        links.append(0)
        state = last
        while state >= 0 and char not in transitions[state]:
            transitions[state][char] = current
            state = links[state]
        if state >= 0:
            target = transitions[state][char]
            if lengths[state] + 1 == lengths[target]:
                links[current] = target
            else:
                clone = len(lengths)
                transitions.append(transitions[target].copy())
                lengths.append(lengths[state] + 1)
                links.append(links[target])
                while state >= 0 and transitions[state].get(char) == target:
                    transitions[state][char] = clone
                    state = links[state]
                links[target] = links[current] = clone
        last = current
    state = size = 0
    for end, char in enumerate(right):
        while state and char not in transitions[state]:
            state = links[state]
            size = lengths[state]
        if char in transitions[state]:
            state = transitions[state][char]
            size += 1
        else:
            size = 0
        if size >= required:
            return right[end - size + 1:end + 1]
    return ""


def inspect_repeated_content(paragraphs, *, previous=()):
    """Detect tiny edits of whole paragraphs and substantial exact copied spans.

    Previous paragraphs are immutable evidence. Returned indices address only
    the new ``paragraphs`` list. Similarity is deliberately high; this helper
    supplements exact duplicate checks rather than claiming plagiarism review.
    Partial copies require a contiguous span of at least 180 normalised chars
    covering at least 35% of the shorter paragraph. For paragraphs <=2000 chars,
    ordered exact blocks >=50 chars can also qualify when one is >=120 chars,
    their sum is >=180 chars and covers >=50% of the shorter paragraph.
    """
    if isinstance(paragraphs, (str, Mapping)):
        paragraphs = [paragraphs]
    if isinstance(previous, (str, Mapping)):
        previous = [previous]
    seen = []
    for value in previous or ():
        text = _body_text(value)
        if isinstance(text, str):
            normal = _duplicate_normalise(text)
            if len(normal) >= 180:
                seen.append(normal)
    issues = []
    for index, value in enumerate(paragraphs or ()):
        paragraph = _body_text(value)
        if not isinstance(paragraph, str):
            continue
        normal = _duplicate_normalise(paragraph)
        if len(normal) < 180:
            continue
        duplicate = False
        shared_span = ""
        shingles = None
        for prior in seen:
            if min(len(normal), len(prior)) / max(len(normal), len(prior)) < 0.985:
                continue
            if normal == prior:
                duplicate = True
            elif max(len(normal), len(prior)) <= 2000:
                duplicate = SequenceMatcher(None, prior, normal, autojunk=False).ratio() >= 0.985
            else:
                # Character shingles keep full-text comparison bounded even
                # for long repetitive Chinese text (quadratic diff is avoided).
                if shingles is None:
                    shingles = Counter(normal[start:start + 3] for start in range(len(normal) - 2))
                old = Counter(prior[start:start + 3] for start in range(len(prior) - 2))
                overlap = sum((shingles & old).values())
                duplicate = overlap / max(len(normal) - 2, len(prior) - 2) >= 0.985
            if duplicate:
                break
        if not duplicate:
            for prior in seen:
                shared_span = _shared_long_span(prior, normal)
                if not shared_span and max(len(prior), len(normal)) <= 2000:
                    # Bounded diff only: long prose keeps the linear span path.
                    # Matching blocks are ordered and non-overlapping on both
                    # sides; short terminology matches never enter the sum.
                    blocks = [block for block in SequenceMatcher(
                        None, prior, normal, autojunk=False).get_matching_blocks()
                        if block.size >= 50]
                    copied = sum(block.size for block in blocks)
                    if (copied >= 180 and copied * 2 >= min(len(prior), len(normal))
                            and any(block.size >= 120 for block in blocks)):
                        shared_span = " … ".join(normal[block.b:block.b + block.size] for block in blocks)
                if shared_span:
                    break
        if duplicate:
            issues.append({
                "code": "near_duplicate_content", "paragraph_index": index,
                "paragraph": paragraph, "claim": paragraph,
                "correction": "该长段与已有正文相同或仅有极少修改；删除重复，提供真正新增的项目设计、检查方法、风险或确认边界。改编号、空白或个别字不能充当新增正文。",
            })
        elif shared_span:
            issues.append({
                "code": "partial_duplicate_content", "paragraph_index": index,
                "paragraph": paragraph, "claim": shared_span,
                "correction": "该段含与已有正文相同的长片段：连续至少180字且占较短段落至少35%，或短段中有序长片段合计至少180字且占至少50%（各片段至少50字且一段至少120字）；删除claim定位的重复片段，保留本段独有内容，并补充真正新增的项目设计、检查方法、风险或确认边界。",
            })
        seen.append(normal)
    return issues


_CHAPTER_CONTRACT_CHINESE_DIGITS = "零〇一二三四五六七八九"
_CHAPTER_CONTRACT_CHINESE_ORDINAL = _CHAPTER_CONTRACT_CHINESE_DIGITS + "十百"
_CHAPTER_CONTRACT_ORDINAL_RE = re.compile(
    r"^\s*第\s*(\d+|[" + _CHAPTER_CONTRACT_CHINESE_ORDINAL + r"]+)\s*章\s*"
)
_CHAPTER_CONTRACT_REFERENCE_RE = re.compile(
    r"第\s*(\d+|[" + _CHAPTER_CONTRACT_CHINESE_ORDINAL + r"]+)\s*章"
)
_CHAPTER_CONTRACT_REFERRAL_START_RE = re.compile(
    r"^(?:这一|这项|这类|这段|这部分|该|上述|其|的表述|的说法|的内容|的描述|的方案|的结论)"
)
_CHAPTER_CONTRACT_INCOMPLETE_END_RE = re.compile(
    r"(?:不能由|尚未|仍需|需要|依赖|包括|包含|基于|通过|针对|在|于|由|与|及|和|但|而|为|是|将|把|按|依据|使用|采用|实现|确保|支持|形成|满足|中|下|的|等|以及|或者|并|可|需)$"
)
_CHAPTER_CONTRACT_HEADING_RE = re.compile(
    r"^(?:第\s*[0-9零〇一二三四五六七八九十百]+\s*[章节]|"
    r"[（(]?[一二三四五六七八九十0-9]+[、.．)）])"
)
_CHAPTER_CONTRACT_HEADING_ENDINGS = (
    "体系", "机制", "方案", "设计", "管理", "概述", "目标", "原则", "流程",
    "架构", "阶段", "措施", "计划", "要求", "范围", "内容", "控制", "策略",
)
_CHAPTER_CONTRACT_SENTENCE_END = "。！？!?；;"
_CHAPTER_CONTRACT_LIST_OR_QUOTE_END = "：:"
_CHAPTER_CONTRACT_CLAUSE_END = "，,、"
_CHAPTER_CONTRACT_DANGLING_PARAGRAPH_TERMS = frozenset({
    "关于", "依据", "通过", "由于", "为了", "鉴于", "根据", "不能由", "这一",
    "对于", "针对", "随着", "因为", "基于", "按照", "依靠", "依赖", "凭借",
    "仍需", "尚未", "需要", "包括", "包含", "将", "把", "以及",
})


def _chapter_contract_number(value: Any) -> int | None:
    """Convert an Arabic or common Chinese chapter ordinal to an integer."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    text = str(value).strip()
    if text.isdigit():
        parsed = int(text)
        return parsed if parsed > 0 else None
    if not text or any(ch not in _CHAPTER_CONTRACT_CHINESE_ORDINAL for ch in text):
        return None
    if all(ch in _CHAPTER_CONTRACT_CHINESE_DIGITS for ch in text):
        digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "三": 3, "四": 4,
                  "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
        return int("".join(str(digits[ch]) for ch in text)) or None
    # Chapter ordinals commonly use 十一, 二十, 二十三, and 一百.
    total = 0
    pending = 0
    units = {"十": 10, "百": 100}
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    for ch in text:
        if ch in digits:
            pending = digits[ch]
        else:
            unit = units[ch]
            total += (pending or 1) * unit
            pending = 0
    result = total + pending
    return result if result > 0 else None


def _chapter_contract_field(chapter: Any, name: str, default: Any = None) -> Any:
    if isinstance(chapter, Mapping):
        return chapter.get(name, default)
    return getattr(chapter, name, default)


def _chapter_contract_outline_items(approved_chapters: Any) -> Iterable[Any]:
    if isinstance(approved_chapters, Mapping):
        chapters = approved_chapters.get("chapters", ())
        return chapters if isinstance(chapters, (list, tuple)) else ()
    return approved_chapters if isinstance(approved_chapters, (list, tuple)) else ()


def _chapter_contract_compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _chapter_contract_chapter_map(
    approved_chapters: Any,
) -> tuple[dict[int, dict[str, str | None]], dict[str, int]]:
    by_number: dict[int, dict[str, str | None]] = {}
    by_id: dict[str, int] = {}
    for item in _chapter_contract_outline_items(approved_chapters):
        title = str(_chapter_contract_field(item, "title", "") or "").strip()
        item_id = _chapter_contract_field(item, "id")
        explicit_ordinal = _chapter_contract_field(
            item, "ordinal", _chapter_contract_field(item, "chapter_number")
        )
        match = _CHAPTER_CONTRACT_ORDINAL_RE.match(title)
        number = (
            _chapter_contract_number(match.group(1))
            if match
            else _chapter_contract_number(explicit_ordinal)
        )
        if number is None or not title:
            continue
        body = title[match.end():] if match else title
        by_number[number] = {
            "id": str(item_id) if item_id is not None else None,
            "title": title,
            "body": _chapter_contract_compact(body),
        }
        if item_id is not None:
            by_id[str(item_id)] = number
    return by_number, by_id


def _chapter_contract_direct_source_prefix(text: str, start: int) -> bool:
    """Accept only source-document wording adjacent to the chapter token."""
    prefix = text[max(0, start - 32):start]
    return re.search(
        r"[^，。；;！？!?\n]{0,24}(?:官方)?(?:文档|手册|指南|标准|规范|资料)"
        r"(?:中的|中|第|的)?$",
        prefix,
    ) is not None


def _chapter_contract_claim(text: str, start: int, end: int) -> str:
    stop = re.search(r"[，。；：:,.;!?！？\n]", text[end:])
    tail = text[end:end + stop.start()] if stop else text[end:end + 48]
    return (text[start:end] + tail).strip()[:96]


def _chapter_contract_fragment_issues(paragraphs: list[str]) -> list[dict[str, Any]]:
    """Find all bounded incomplete / short-phrase / backward-reference runs."""
    issues: list[dict[str, Any]] = []
    for middle_index in range(1, len(paragraphs) - 1):
        previous = paragraphs[middle_index - 1].strip()
        middle = paragraphs[middle_index].strip()
        following = paragraphs[middle_index + 1].strip()
        compact_middle = _chapter_contract_compact(middle)
        if not previous or not middle or not following:
            continue
        if len(compact_middle) > 32 or any(
            ch in middle
            for ch in _CHAPTER_CONTRACT_SENTENCE_END + _CHAPTER_CONTRACT_LIST_OR_QUOTE_END
        ):
            continue
        if _CHAPTER_CONTRACT_HEADING_RE.match(middle) or compact_middle.endswith(
            _CHAPTER_CONTRACT_HEADING_ENDINGS
        ):
            continue
        previous_compact = _chapter_contract_compact(previous)
        if previous.rstrip()[-1:] in (
            _CHAPTER_CONTRACT_SENTENCE_END
            + _CHAPTER_CONTRACT_LIST_OR_QUOTE_END
            + _CHAPTER_CONTRACT_CLAUSE_END
        ):
            continue
        if not _CHAPTER_CONTRACT_INCOMPLETE_END_RE.search(previous_compact[-16:]):
            continue
        if not _CHAPTER_CONTRACT_REFERRAL_START_RE.match(
            following.lstrip(" \t\r\n\"'“‘（([")
        ):
            continue
        issues.append({
            "code": "fragmented_quoted_paragraph",
            "paragraph_index": middle_index - 1,
            "claim": " / ".join((previous, middle, following))[:160],
            "correction": (
                "请修正拆段并返回本批全部完整正文；检查器不会自动合并或改写这些片段。"
            ),
        })
    return issues


def _chapter_contract_dangling_paragraph_issues(paragraphs: list[str]) -> list[dict[str, Any]]:
    """Find paragraphs consisting only of a known dangling function phrase."""
    issues: list[dict[str, Any]] = []
    for paragraph_index, paragraph in enumerate(paragraphs):
        compact = _chapter_contract_compact(paragraph).rstrip(_CHAPTER_CONTRACT_SENTENCE_END)
        if compact not in _CHAPTER_CONTRACT_DANGLING_PARAGRAPH_TERMS:
            continue
        issues.append({
            "code": "dangling_paragraph",
            "paragraph_index": paragraph_index,
            "claim": paragraph,
            "correction": (
                "请修正悬空片段，并返回本批全部完整正文；检查器不会自动重写或合并段落。"
            ),
        })
    return issues


def inspect_chapter_contract(
    paragraphs: Iterable[str],
    *,
    approved_chapters: Any,
    current_chapter_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return location-specific contract issues without changing input text.

    Cross-chapter project references must use the approved full title directly
    after the explicit ordinal. A bare ordinal is permitted only for the
    current chapter. Source-document chapter citations are exempt only when
    source wording is lexically adjacent to that citation.
    """
    paragraph_list = [p if isinstance(p, str) else str(p) for p in paragraphs]
    chapter_numbers, chapter_ids = _chapter_contract_chapter_map(approved_chapters)
    current_number = chapter_ids.get(str(current_chapter_id)) if current_chapter_id is not None else None
    issues: list[dict[str, Any]] = []

    for paragraph_index, paragraph in enumerate(paragraph_list):
        for match in _CHAPTER_CONTRACT_REFERENCE_RE.finditer(paragraph):
            if not chapter_numbers:
                break
            if _chapter_contract_direct_source_prefix(paragraph, match.start()):
                continue
            referenced_number = _chapter_contract_number(match.group(1))
            claim = _chapter_contract_claim(paragraph, match.start(), match.end())
            if referenced_number is None or referenced_number not in chapter_numbers:
                issues.append({
                    "code": "unknown_approved_chapter_reference",
                    "paragraph_index": paragraph_index,
                    "claim": claim,
                    "correction": "请依据批准目录中的实际章节改写为完整章节标题，或删除该项目章节引用；不要推测章节映射。",
                })
                continue
            if referenced_number == current_number:
                continue
            chapter = chapter_numbers[referenced_number]
            expected_body = str(chapter["body"] or "")
            suffix = _chapter_contract_compact(paragraph[match.end():])
            if expected_body and suffix.startswith(expected_body):
                continue
            expected_title = str(chapter["title"])
            issues.append({
                "code": "approved_chapter_reference_mismatch",
                "paragraph_index": paragraph_index,
                "claim": claim,
                "correction": f"请将跨章引用改为批准目录中的完整标题“{expected_title}”，或删除该引用。",
            })

    issues.extend(_chapter_contract_dangling_paragraph_issues(paragraph_list))
    issues.extend(_chapter_contract_fragment_issues(paragraph_list))
    return issues

# 原表本地库真实自然语言、固定快照及 XLSX 子项

2026-10-17 20:05—20:08（Asia/Shanghai）。关联 AI-T08/AI-T14/AI-T15，AI-AC05/08/12/18 子项。结果：**部分通过；原始声明的助手证据链缺口未通过**。本证据不代表全部验收或全库研究完成。

## 环境与操作

- 所属本地服务 `http://127.0.0.1:13180`，当前原表规范企业1283家；产品角色通过实际登录、业务关联、助手HTTP API操作。无mock，无附件，未改前端、全局开关、权限、企业及旧资质。
- 使用 `.runtime/company-test/python/Scripts/python.exe`（Django及openpyxl已安装）。私有程序和完整收据在ignored的 `.runtime/baichuan-ai-local/public-query-acceptance/`；`verify.py`拒绝有收据时重新提交，`finish_existing.py`仅读取已提交任务并幂等导出，不含消息提交。
- 先核查worker `_conditions`、portal `generate_for_use`与transport非流式调用：一次条件理解调用，无自动重试。研究开关false立即返回缺口，Excel无模型调用。只发送公开通用需求“找电子与智能化工程专业承包二级企业”，模型上下文仅系统条件规范、该需求、查询日期和空历史/附件，不含企业名册、电话或内部文件。
- 搜索、研究、事实写入仍关闭。创建1个新会话、1个查询、2个固定快照导出任务；历史9会话全部保留。

## 实际结果

- 查询耗时4.595秒；ModelCallLog从5到6，唯一新增记录success，2598毫秒，输入780/输出212tokens。任务 `_budget_model_calls=1`、`_budget_sources=0`；未重发自然语言、未执行研究重试。
- 真实模型输出硬条件 `must.all=[{field:qualification,category:electronic,op:grade_exact,value:"2",holder:bidder}]`，should/unresolved均空；精确二级未扩大为及以上。
- 固定快照 `e3c2e551-5cd7-4534-808b-8c41c422d78e`，1283候选、0确认、0排除。原表证书未经主体/正文/日期等独立核验，因此unknown，未当作合格企业。查询任务partial，明确“自动公开资料研究尚未启用”。
- 默认导出实际下载9218字节XLSX，三表均0数据行；显式包含候选并limit10的下载11295字节，企业结果0行、逐项依据10行、待核实信息10行。openpyxl真实读取三表，候选均标“待核实候选”，判断“未知”、日期“未核实”，没有公式单元格。两个文件均含同一快照/条件版本/截止时间；HTTP实际 `Cache-Control:no-store`、`X-Content-Type-Options:nosniff`。
- 企业/旧资质/人员全字段摘要前后一致：`724750bb86495c671d0135e271ac6d4563f788ff4a0fae815a9e4312301d093d`；历史消息摘要前后一致；快照条件、结果和计数摘要前后一致。新增数据限本次合法会话/任务/快照/导出及其审计。

## 发现与边界

**来源追溯未通过：** 全快照所有逐项 `evidence_ids` 均空。只读核查实际1460个映射证书（其中electronic414）全部 `certificate.evidence=NULL`；原完整source已留在旧资质与mapped_declaration修订，但尚未连为助手Evidence。因此API不能返回源表原文行定位，候选XLSX相应写“来源未包含在授权快照证据范围”。不能将本轮标为逐项来源完整通过。后续应增量创建未核实来源证据并连接映射证书，保留旧实体/旧修订/旧快照，不提升核实状态；实际批量前需新备份、权限和版本校验、精确来源匹配、幂等与摘要验证。

最初终端显示的理由乱码经独立码点核查证实是Python终端编码展示问题：DB、HTTP JSON和磁盘AST中文完全相同，U+FFFD数量0，新进程代码常量相同。`reason-encoding-audit.json`保存码点与hash，无业务乱码，不需改理由或重启修复。私有验证器也修正了“首屏必须有证据”及XLSX尾部元数据空列的错误假设，没有据此重发模型。

本单元验证真实原表本地库的自然语言到快照与下载路径；历史官网研究未恢复、字段核实仍0、研究仍关闭。没有公开页面查证、文件理解、浏览器全交互或远程生产验收，不外推这些能力。

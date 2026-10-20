# AI-T08 / AI-T09 / AI-T14 / AI-T15：夜间真实文字、文件与导出验收

执行时间：2026-10-17 23:46:28–23:50:10（北京时间）。目标为本任务所属本地服务与已接入原名录的1283家企业库；不是远程生产验收。执行前根代理已完成仅后端重载；本单元没有更改业务代码、页面或服务进程。资料写入在验收期间暂停。

## 输入与真实结果

通过 `http://127.0.0.1:13180` 实际鉴权 HTTP API，分别使用现有 product、general_manager 两角色。每角色执行三个场景，共6个真实模型查询：

1. 公开合成文字要求：投标人电子与智能化工程专业承包**精确二级**，输出名称、电话。模型保留精确等级和投标人主体。
2. 同一会话连续追问：保留前轮硬条件，增加 ITSS 二级为评分优先项。生成修订2，未将优先项改成硬条件；重新读取会话可恢复两轮消息。
3. 仅上传合成 DOCX、文字为空：投标人电子二级硬条件、ITSS二级评分、制造商CCRC二级、项目负责人个人CISP。实际附件解析 completed，条款来源可定位到该附件的块。CCRC归于制造商；未支持的个人CISP明确保留在 unresolved，不误归投标企业。实际制造商等级被提取为至少二级，未据此授予企业满足结论；但原文没有“及以上”，这属于等级扩大缺口，随后按AI-D23修正复验。本轮六场景未断言CCRC精确关系，不能用该收据放行这一新增子项；原结果保留。

六个固定快照均为 confirmed=0、candidate=1283、excluded=0。原表资质缺少独立核实证据，未知保持未知；非空候选不能解释为满足资质。逐项理由存在，原名录 evidence 的 excerpt 与 sheet/row 可通过结果 API 定位，不向读者提供存储路径等私有 locator。

每角色实际生成并下载默认确认结果、显式包含候选的两份 XLSX，共4份。每份均实读三张表：企业结果、逐项依据、待核实信息；默认确认结果0家，显式候选为固定快照前10家。名称/电话与快照逐项相等，未产生公式单元格；依据表含原表 sheet/row，下载响应为 XLSX、no-store、nosniff。

两角色双向访问对方会话、任务、快照和导出下载均返回404，共8个越权检查。六个已生成快照在连续追问和导出后摘要不变。

## 首次失败与不重复恢复

第一次程序在 product 的文件场景后停止，原断言强制要求 must 中出现 person 谓词。实际 CISP 类别未支持，模型在 unresolved 明确保留“项目负责人个人CISP证书……主体为人员……需核实”，符合保守保留规格。这是验收器过严，不是证书误归属；没有修改业务实现或降低“不得丢掉/误归属”要求。

原失败收据及原验收器单独归档后，验收器改为允许 CISP 的明确人员谓词，或明确人员/CISP未支持待核实说明；任何 CISP 误归 bidder 等其他主体均拒绝。新增纯测试覆盖正确 unresolved、缺失、模糊说明、错误主体、正确人员谓词。

直接 GET 实际 API 确认说明包含可读中文，无字面 `\\u` 转义；先前 SQLite JSON 层显示的转义不能当作界面乱码。ModelCallLog没有保存上游原回复，未为诊断追加模型调用。

恢复执行沿用预写的 client_request_id 和已返回资源ID；三个原任务重新 GET，未重新提交或执行模型。第一次退出1，第二次退出0，两次日志均保留。通过收据仍保留首次失败的历史 error 字段；最终判定字段为 `status=passed`，原失败版本另存且不覆盖。

## 实际用量与数据保护

- 新增 ModelCallLog **6条，全部 success**；每个查询 job 的 `_budget_model_calls=1`，总计6，无重试任务。模型用时合计20943ms，输入5986、输出1690 tokens。
- 遵循用户“没有模型预算”的新指令，没有新增人工调用上限；原显式任务预算、有限失败重试、防重复提交机制保留。
- 所有查询 `_budget_sources=0`，research_status=not_requested；查询不会触发联网补齐。
- Company、CompanyQualification、CompanyPerson 全表有序摘要前后相同；1283家保留。历史11个会话及其消息/快照摘要相同。Evidence、FactRevision、ResearchManifest、ResearchItem及 research job 数量相同。
- 输入模型的是公开合成检索要求与合成文件，没有企业名册、企业联系方式、内部文件。验收器只读查询数据库；写入仅由已授权业务 API 建立本轮会话、任务、快照、导出和调用日志。

## 命令、收据与恢复点

仓库根目录执行（本轮已经运行，**不要再次当新验收提交**）：

```powershell
.runtime/company-test/python/Scripts/python.exe .runtime/baichuan-ai-local/night-acceptance-20261017/static-check.py
.runtime/company-test/python/Scripts/python.exe .runtime/baichuan-ai-local/night-acceptance-20261017/real-query-files.py --execute
```

静态检查在临时目录运行，SQL、DNS和网络入口均禁止；结果PASS。验证了DOCX内容、提交ID先落盘、重复提交抑制、不确定响应只读找回、poll-only不提交，以及上述人员缺口断言。真实执行第二次结果：`passed / cases=6 / actual_model_log_delta=6 / exports=4 / catalog_preserved=true`。

私有目录 `.runtime/baichuan-ai-local/night-acceptance-20261017/`：

- `receipt-passed-002.json`、`receipt.json`：通过收据与完整保护摘要、6任务/快照和4导出ID。通过时 SHA256 `32741153dd7bdb4d35c7b708481f679a5992824b54efb3a60d2524705ac55a05`。
- `receipt-failure-001-person-assertion.json`：原失败，SHA256 `336cb1bed84f0fd9235fb8b6dce22c999af838df725a6978d64018886af4bd56`。
- `real-query-files-failure-001.py`：原验收器，SHA256 `d1b01621a6978ced3ed92691579da7b23acf7ea8084c7241d30778d70f266b3b`。
- `real-query-files.py`：修正验收器，SHA256 `6db491ba85a93df1d80c2906a7cc9f04441d41ec4f6bedfd0a8ea019ce3ef986`。
- `failure-001-person-diagnostic.json`：仅真实GET与只读库诊断。
- `execute-001.log` / `execute-002-resume.log`：原失败与恢复日志。
- 六份 `*-located-api.json`、四份角色/范围对应 `.xlsx`：实际API依据与下载内容，限本机私有保存，不作为公开名册附件。

若只需恢复轮询，使用 `--poll-only`，只恢复已提交ID并GET现有任务，不新建查询/上传/导出。当前验收已完成，无待重试任务。此证据不代替前端浏览器、远程部署、PDF/OCR真实输入、真实取消/进程崩溃或全库字段研究验收；后者由各自独立证据承担。

# AI-T14 固定快照 XLSX 导出与下载验证

日期：2026-10-17（北京时间）；基线 HEAD `ef1676cd8327d693dab897c45a234ba91413884e`，含当前增量工作区。实现：`portal/baichuan_exports.py`、独立 `portal/baichuan_export_api.py`、`portal/tests/test_baichuan_exports.py`，并扩展 `baichuan_jobs.retry_job` 的请求完整性及导出重试记录。没有真实企业库写入或远程部署。

## 复查与实际结果

```powershell
& .runtime/company-test/python/Scripts/python.exe doc/baichuan-sdd/ai-assistant/evidence/AI-T02/probe_capabilities.py --export-tests
& .runtime/company-test/python/Scripts/python.exe doc/baichuan-sdd/ai-assistant/evidence/AI-T02/probe_capabilities.py --job-export-tests
```

Python 3.13.16、Django 5.2.18、openpyxl 3.1.5；虚构企业、证据、账号及固定快照，隔离 SQLite 迁移至 0046，临时 XLSX 在临时受控存储创建，结束清理。最终实际合跑结果：**30 tests / 25.183s / OK**（15 个任务测试 + 15 个导出测试）；Django system check、`git diff --check` 通过。没有模型/搜索调用、真实导出或生产变更。

## 已验证行为

1. 文件确为 ZIP/OOXML XLSX，openpyxl 可实际回读；包含“企业结果”“逐项依据”“待核实信息”三表。各表记录固定快照 ID、条件版本、结果修订、数据截止时间、研究状态、导出时间、实际数量和范围。
2. 默认只选择 confirmed，默认数量遵守原查询 `output.limit`；指定前 N 条及 fields 生效。显式 `include_candidates=true` 才选择候选，候选放入“待核实信息”，不混作已确认企业；excluded 不导出。
3. 全部单元格以 OOXML 字符串和文本数字格式写入；电话、信用代码、证号类字符串的前导零保留。实际 `=HYPERLINK(...)`、`+虚构企业B`、`@虚构候选C` 回读仍为字符串，所有单元格均无公式类型、无超链接。
4. 逐项依据包含企业、condition_id、判断、原因、证据 ID、公开来源、核验日期和原文定位。证据必须属于同部署 scope 和该企业主体；来源只导出公开 HTTP(S) URL 或来源标题，不导出内部 import_ref/storage_ref/本机路径。
5. 字段不在原固定快照中时留空并在说明中明确，不读取后来改动的企业事实。创建新研究修订后，旧导出字节及 hash 完全一致。
6. 空结果导出只有真实范围、零数量和表头，没有虚构企业。条数、单元格长度、依据行数和文件大小有明确上限（5000 企业、32767 字符/单元格、100000 行/表、20 MiB），超限明确拒绝；不静默截断为“完整导出”。依据行数在分配工作表前预检，证据按 500 个 ID 批量读取。
7. 幂等键相同参数只建一个 job/export；同键改变范围 409。结果修订不符、无效字段、布尔伪整数和不明确候选范围拒绝。
8. 所有者、当前百川读取权限、会话/任务部署 scope 在排队、生成、下载时重查。别人的导出统一 404；撤权后拒绝下载；过期 410、未就绪 409、文件缺失 410、内容/hash/大小不符 409。
9. UUID 存储键由服务端生成，路径必须经过现有 storage_path 校验；文件先独占创建并 fsync，再在 leased_job 短事务内同时发布元数据、hash、结果引用和 completed。模拟落盘后数据库提交故障时清理孤儿文件；租约过期后新 fence 可恢复生成。模拟旧 worker 落盘后新 worker 接管，旧 fence 发布被拒绝且旧临时文件删除。
10. 导出失败后经现有 HTTP retry API 创建新尝试，再由真实 `run_one` 领取并完成新 XLSX；新 BaichuanExport 引用同一不可变快照并使用新文件。原记录/文件不改写。原请求 hash 或快照授权/selection 不一致时不创建重试。
11. 实际调用独立 HTTP endpoints 验证 202 排队、别人的下载 404、正确下载 200，响应为 XLSX attachment，`Cache-Control: private, no-store`、`X-Content-Type-Options: nosniff`，流内容 hash 一致。
12. 默认保留期限 86400 秒，可配置为 60—604800 秒；expire_exports 是有界维护 hook（默认 100 条），过期文件删除后保留快照、hash、审计与导出记录，不将清理当作删除业务资料。未在本轮创建后台定时器或远程清理任务。

## 检查中修复

- 首轮空结果测试将无扩展名的受控 UUID 文件路径直接传给 openpyxl，阅读器因文件名后缀拒绝；改用二进制流回读后通过，下载文件本身为标准 XLSX。
- APIRequestFactory 直接关闭 FileResponse 会发 request_finished 信号，提前关闭 TestCase 外层文件 SQLite 事务；测试改为只关闭文件流，生产响应关闭行为不改。
- 审阅发现通用 export 重试缺关联记录；补充独立记录克隆与完整请求 hash 检查，并加入实际 API → worker 的回归测试。
- 审阅发现 import_ref 可能含私有路径；改为公开 URL/脱敏来源标题，并有路径不泄露断言。

## 依赖和恢复入口

复用现有 openpyxl 3.1.5（MIT）与 et_xmlfile 2.0.0；`deploy/cloud/requirements.lock` 已锁定二者，原 parser requirements 也已有。为 Windows 业务后端补充可选精确声明 `services/business/requirements-baichuan-export-python.txt`，本轮没有执行安装或升级。缺库时 lazy import 返回明确 503，能力页面通过 export_available 检测，不能用本地可用冒充目标环境已部署。

服务契约：`enqueue_export(user,snapshot_id,payload) -> job`；`process_export(job,worker) -> export`；`open_export(user,export_id) -> (export,stream)`；`expire_exports(limit=100) -> deleted_count`。独立 API：`baichuan_export_api.exports(request,snapshot_id)`、`download(request,export_id)`，路径由主执行者接入既有百川 URL。整体 UI 联调、目标环境真实账号下载和五千家规模性能仍由 AI-T15/16/17 继续验证，本证据不宣布目标部署或全库资料补全完成。

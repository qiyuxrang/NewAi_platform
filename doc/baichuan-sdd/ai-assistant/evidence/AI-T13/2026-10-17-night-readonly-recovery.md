# AI-T13 / AI-AC10：既有真实会话的浏览器恢复验收

时间：2026-10-17 23:55:18–23:55:31（北京时间）。结果 **PASS**。使用本机 Python3.14 的 Playwright 与 urllib，启动独立 headless Microsoft Edge；没有控制用户浏览器、修改页面代码/CSS/DOM实现或重启服务。

## 范围与方法

复用 [本轮真实文字/文件验收](../AI-T15/2026-10-17-night-real-query-files.md) 已生成的 product、general_manager 两角色文字会话、连续追问快照和4个导出。读取 `BaichuanAssistant-data.ts` 的 `assistantStorageKey`，按真实 origin、平台 owner id、portal owner id，将对应既有会话ID写入各自独立 context 的 localStorage；仅浏览器上下文保存内存中的本地认证 token，不记录凭据或 token。

浏览器请求守卫只允许 `127.0.0.1:13180` 的读取请求及本地认证、enterprise/link。所有业务 POST/PATCH/PUT/DELETE 均拦截并计入失败；没有查询、上传、取消、重试或新导出。urllib 客户端同样只允许鉴权例外和读取，禁环境代理和重定向。普通网页行为保持原样。

两角色各实际完成：

1. 页面默认收起；真实刷新后仍收起，点击角色入口后恢复两条用户消息及已有助手回复。
2. 逐字断言文字请求和连续追问可见；当前修订2的准确快照ID由真实 GET 结果请求确认，显示50条待核实候选、总数1283。
3. 点击两个已有“下载 Excel”按钮，仅GET既有文件；实际下载4份，与前轮对应默认确认/显式候选 XLSX 的 SHA256 集合逐一相等。
4. “在列表查看”显示固定快照准确ID及条件版本2；点击候选进入企业详情，固定列表退出且详情标题与点击企业相等；返回后原手工筛选 `electronic=2` 保留。
5. 重开助手、收起、真实刷新、再打开，仍恢复原两轮消息及50条结果，localStorage中的会话ID不变。

本轮仅验收**已完成任务的刷新/关闭恢复**；没有声称测试任务在途时关闭仍继续。未新增查询或模型调用，也未通过DOM伪造消息/结果。

## 保护核账与实际检查

- 两角色通过；浏览器API读取记录107条。
- 业务 mutation 请求0，外部请求0，pageerror0；4个下载文件校验相同。
- 前端冻结清单全部 **163文件 SHA256一致**。
- Company、CompanyQualification、CompanyPerson有序全表摘要前后相等。
- 验收前所有已有会话及其消息、快照（含刚完成的真实查询快照）摘要前后相等。
- Evidence、FactRevision、ResearchManifest、ResearchItem及独立 research job 数量相等；ModelCallLog增量 **0**。
- Python编译检查通过；实际执行退出0。未写业务数据库；允许的登录/账号绑定走现有API。

## 复查材料与恢复点

本轮已实际运行，不需再次重复：

```powershell
py -3.14 -m py_compile .runtime/baichuan-ai-local/night-acceptance-20261017/readonly-browser.py
py -3.14 .runtime/baichuan-ai-local/night-acceptance-20261017/readonly-browser.py
```

私有目录 `.runtime/baichuan-ai-local/night-acceptance-20261017/`：

- `readonly-browser.py`：SHA256 `3535b33010b5eff973b1aa234b7f657170bf7c248c218efefca14fad6717756d`；拒绝覆盖已存在的运行目录。
- `readonly-browser-001.log`：实际通过摘要。
- `readonly-browser/receipt.json`：SHA256 `6aa3eb9e033e620c870c83a3a90a0855ccd5ec04e7c437e36680f4dddf6c832a`，包含精确会话/快照ID、请求路径及所有断言结果，不含 token。
- `readonly-browser/before.json`、`after.json`：只读摘要与模型调用元数据。
- 两角色 `*-restored.png` 与四份 `*-existing-*.xlsx`：真实页面截图和既有下载，包含企业资料，限本机当前用户ACL保存，不加入仓库。

全部浏览器与 context 已正常关闭；本地业务服务及前端进程保持原状。本证据不替代前端视觉改造、输入法专项、真实在途取消/崩溃、远程生产部署或全库资料核实验收。

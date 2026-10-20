# AI-T15 合并回归与恢复点

日期：2026-10-17；代码为 HEAD `ef1676cd8327d693dab897c45a234ba91413884e` 加当前工作区。本轮未提交、推送或修改远程生产。所有后端测试由 `scripts/baichuan/check_backend.py` 清除继承 PORTAL 配置并建立临时文件 SQLite/私有存储，不使用实际企业库。

## 原业务回归

实际命令：

```text
.runtime/company-test/python/Scripts/python.exe scripts/baichuan/check_backend.py portal.tests.test_baichuan portal.tests.test_baichuan_import portal.tests.test_baichuan_source
```

第一次 Django 默认共享内存 SQLite：35 tests /30.407s /OK，skipped=1；跳过的原编辑并发测试明确要求文件 SQLite，不能算该项通过。修改隔离检查入口，设置临时目录内专用 TEST.NAME 并在 finally 关闭连接后完整重跑：**35 tests /34.362s /OK，零跳过**。system check 0 issues。两会话同时维护时仅一份快照提交，另一份版本冲突；原字段、来源、精确筛选和访问边界通过现有回归。

WhiteNoise 提示未收集 staticfiles 目录，为当前测试环境提示；未隐藏告警、未以此声称目标发布已验证。

## 合并检查

实际执行以下 12 模块（同一命令、同一全新临时文件 SQLite，包含迁移往返和独立 OS 进程竞争）：

```text
.runtime/company-test/python/Scripts/python.exe scripts/baichuan/check_backend.py portal.tests.test_baichuan portal.tests.test_baichuan_import portal.tests.test_baichuan_source portal.tests.test_baichuan_assistant_models portal.tests.test_baichuan_conditions portal.tests.test_baichuan_assistant portal.tests.test_baichuan_facts portal.tests.test_baichuan_jobs portal.tests.test_baichuan_research portal.tests.test_baichuan_research_runtime portal.tests.test_baichuan_exports portal.tests.test_baichuan_integration_review
```

实际结果：**139 tests /115.706s /OK，零跳过**；system check 0 issues。覆盖原企业 CRUD/来源/导入、增量迁移往返、四态规则、权限/版本/租约/幂等/并发、对话与真正 DOCX 子进程解析、快照与组合导出、事实保护、全库固定清单、研究缓存/引用/有限核验与原生 XLSX 读取/授权。

同批 `git diff --check` 退出 0；SDD validator 为 23 Markdown、24 本地链接、14 需求、18 任务、20 验收，errors=[]。该文档校验数值随新增证据变化，不属于产品验收。

前端最终 101/101、TypeScript/Vite/定向 ESLint 及真实模型浏览器结果见 [UI证据](../AI-T13/2026-10-17-local-ui.md)；结构化性能见 [基准](../AI-T16/2026-10-17-structured-benchmark.md)。本轮整体回归后继续补“明确取消文件硬条件”和多轮条件去重窄单元；该变更需另行检查，不能自动沿用本节通过状态。

## 第二轮完整合并回归

文件明确取消/多轮去重与关联重试计数修复后，在上节命令后增加 `portal.tests.test_baichuan_file_conditions`，完整 13 模块再次执行：**156 tests /118.274s /OK，零跳过**；system check 0 issues。新增文件取消 16 项及关联重试 1 项实际纳入同一文件 SQLite 测试库，原 12 模块一并通过。

该轮启动后最终审阅又发现“取消命令与新附件同时提交→澄清文字回复”的待附件续接风险；该补丁以之后专项检查为准，不将上节156项结果直接声称为该补丁已经通过。无关旧 CRUD/迁移/导出未再变更。

这些结果属于隔离实现验证，未连接真实企业、未进行目标环境迁移或全库资料研究，不能作为 AI-AC18/19 通过依据。

## 最终补丁专项回归

最终代码冻结前，对 `test_baichuan_file_conditions`、`test_baichuan_integration_review`、`test_baichuan_assistant`、`test_baichuan_conditions` 执行专项：**57 tests /37.406s /OK，零跳过**（19+19+11+8）。覆盖待附件续接、同用户/会话权限、解析复用、模型连续失败后重试、稳定payload/hash、文件硬条件保护和旧城市文字隔离、缺版本字段的导出失败回复及安全超时提示。首轮发现旧城市文字被误归文件条件，修复并再次通过全部57项。命令与失败/修复记录见 [最终文件条件证据](2026-10-17-file-condition-relaxation.md)。

156项完整回归在该补丁之前，57项是该补丁后的实际结果，不能相加。无关原业务检查未无故重复。代码已冻结，最终仅本任务所属服务重启加载代码；不新增模型调用或操作原企业资料。

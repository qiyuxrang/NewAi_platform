# 百川助手本地运行与恢复

在项目根目录运行以下 PowerShell 命令。启动器只管理带本任务所有权标记的进程；数据库和凭据留在 ignored `.runtime/baichuan-ai-local`，重复启动不会清库。

```powershell
& '.runtime/company-test/python/Scripts/python.exe' scripts/baichuan/local_dev.py start
& '.runtime/company-test/python/Scripts/python.exe' scripts/baichuan/local_dev.py status
```

页面：<http://127.0.0.1:13180/departments/product/baichuan>。专用本地账号保存在 `.runtime/baichuan-ai-local/accounts.json`，不要将该文件提交或复制到开发证据。当前已接入用户原名录1283家，标签为“本地源表资料，历史官网补查未恢复”；没有已完成接入收据的新环境才显示未连接的空库标签，不能将其当成真实库为空。

后端使用 `--noreload`，修改后端后应 stop/start；已提交任务、会话、附件和结果留在数据库。停止命令仅停止仍能验证归属的进程：

```powershell
& '.runtime/company-test/python/Scripts/python.exe' scripts/baichuan/local_dev.py stop
& '.runtime/company-test/python/Scripts/python.exe' scripts/baichuan/local_dev.py start
```

助手工作进程由启动器独立运行，收起面板、刷新页面不会取消任务。失败尝试保留错误、预算、检查点及结果，可在面板显式重试；模型调用与公开网页访问的失败不能作为匹配满足依据。

`local_model.py` 仅复用本机既有私有配置，并只注册隔离库路由；探测有防止隐式重复调用的收据。已配置完成时普通 stop/start 会恢复所属模型网关，无需再次 configure/probe。搜索配置缺失时如实显示缺口，不创建密钥、不采购服务。

启动器为本地 portal 与 baichuan-worker 固定设置本项目 `services/business` 的绝对 `PYTHONPATH`，覆盖继承值；模型网关沿用相同仓内路径。`local_model.application()` 同时设置已运行解释器的 `sys.path`，供操作脚本导入公开网页传输。其他部署的 portal/worker 也须在各自服务环境配置对应仓库的绝对 `services/business` 路径，使 `model_gateway` 可导入；本脚本不会修改那些部署。

## 检查

后端入口清除继承的 `PORTAL_*` 配置，建立专用临时文件 SQLite 和私有存储；只接受明确的百川测试模块：

```powershell
& '.runtime/company-test/python/Scripts/python.exe' scripts/baichuan/check_backend.py portal.tests.test_baichuan_assistant portal.tests.test_baichuan_conditions
& '.runtime/company-test/python/Scripts/python.exe' doc/baichuan-sdd/ai-assistant/validate_sdd.py
```

结构化性能样本由 `benchmark_matching.py` 独立生成，不向页面或目标库添加测试公司。真实浏览器验证由 `verify_local_browser.py` 执行，运行前阅读该脚本的参数和模型调用预算，避免重复调用。截图及原始收据留在 private runtime，开发文档只放脱敏结论。

端到端确定规则容量检查使用独立临时 SQLite/存储，禁止模型和全部 socket 连接，不访问现有资料库或常驻服务。它经正常消息入队，在私有测试任务放入已校验条件检查点，再运行真实 worker、固定快照、导出消息、worker 和授权下载，逐行重读三张 XLSX 表。该检查排除模型理解、HTTP/浏览器和公网延迟，不能作为自然语言端到端验收。

```powershell
& '.runtime/company-test/python/Scripts/python.exe' scripts/baichuan/benchmark_assistant_e2e.py --output '.runtime/baichuan-checks/e2e-new-receipt.json'
```

默认1000/5000家，每规模1个关闭连接后的首样本及3个热样本，硬上限540秒；输出路径必须不存在。最近秩P95在3个热样本时是最大值，只供本机有限样本比较。`--sizes 100 300 --warm-samples 0` 可先小样估计；`--profile-max-row` 单独记录工作表扫描耗时，`--compare-row-algorithm` 使用同一快照和导出时间比较旧行扫描/现行计数算法，并断言三张表、样式及工作簿XML相同。这两个诊断模式与常规耗时分开记录。

## 接续真实资料

当前已接入用户提供的原名录，尚未定位历史百川研究数据库及补充研究Excel。恢复实施先读 SDD 的 `progress.md`、`checkpoint.json`，不要把本地源表接续或历史数量当成旧研究库恢复。若找到历史SQLite，先显式只读盘点：

```powershell
& '.runtime/company-test/python/Scripts/python.exe' scripts/baichuan/inventory_sqlite.py --sqlite '实际已存在的数据库完整路径'
```

该脚本采用 `mode=ro`、`query_only=ON`，缺表输出 null，不创建数据库。真实资料接入前还需确认部署、字段/ID、来源与备份；本启动器不会代为初始化真实库。目标环境使用原权限与模型网关，增量迁移为 `0046_baichuan_assistant_foundation`；助手、研究、事实写入有独立开关，默认关闭。关闭新开关不删除已有企业与修订历史。

全库研究须由维护身份创建固定ID清单，并满足真实数据标记和备份引用约束。覆盖报告分别统计访问尝试、有效研究和已核实字段；查不到、访问失败、仅提取到建议均不能写作已核实。当前已有本地原表固定清单，访问失败的首家试查不代表有效全库研究；远程生产部署未执行。

## 2026-10-17 原名录接续状态

用户随后提供与历史源件指纹一致的多表名录，已在同一owned本地库恢复1283规范企业、1462原始声明（1460分类声明）、1024家原表电话；原会话/权限保留。页面标签改为“本地源表资料，历史官网补查未恢复”。`source-status.json`只在成功导入及复查后写入，保留isolation部署属性与local_source_only标识，不宣称找到旧正式库。不要重新执行初始化或清库。

可复用的只读归一入口为 `portal/baichuan_source_workbook.py --input <原件> --output-dir <全新私有目录>`，需company-test已有defusedxml0.7.1；仅新建JSON，拒绝覆盖。总表/七分类先严格核账，再经既有convert_source与导入预检；禁止把聊天上传入口变成覆盖导入。实际转换、备份、已复核清单、提交/幂等回执均在 `.runtime/baichuan-ai-local/source-restore-220ec53e/`，恢复先查回执，不重复接入。

`verify_source_snapshots.py` 与 `verify_source_browser.py` 是本地确定规则/真实UI验收工具，前者会创建明确标注的私有测试会话及导出，必须先读其执行开关和拒绝重复写入约束；不能当作自然语言或联网研究证据。两角色当前结果见私有 `source-browser-verification/results.json`，无模型/出站请求。版本规则已显式安装7条，源表证书声明仍unverified。下一步联网研究与旧研究库合并以SDD最新检查点为准。

`research_source_pilot.py` 默认只说明、不写库/联网；显式execute须提供完整源指纹和实际能力收据。当前固定清单1283家/15396项，仅首家已作有界访问尝试：12项inaccessible、0正文/模型/独立核实，原主资料未变，重复命令只读回。私有 `research-source-220ec53ebe6a/pilot-receipt.json` 保存结果与恢复点，不能自动重试、扩批或缩小分母。

本地实验性 `bing_rss` 默认关闭，虽然通用请求能取得RSS，但实际企业相关性失败，不得据此启用批量研究。runtime已拒绝标题/摘要不含完整企业名的线索，旧策略缓存保留不复用。常驻服务的搜索、研究和事实写入保持关闭，替代来源验证以最新SDD证据为准。

## 本地搜索凭据准备（保持关闭）

`local_search.py` 仅将用户已有的 Tavily 或 Brave 密钥配置到所属本地环境；不采购、不联网、不启动服务。先把密钥保存为单行 ASCII 文本文件，再执行：

```powershell
& '.runtime/company-test/python/Scripts/python.exe' scripts/baichuan/local_search.py
& '.runtime/company-test/python/Scripts/python.exe' scripts/baichuan/local_search.py configure --provider tavily --key-file '用户提供的密钥文件完整路径'
# Brave 改用 --provider brave；不要把密钥本身放在命令行。
```

输出只显示配置状态、provider、masked 及 `quality_not_validated`。`search-credentials.json` 在写入密钥前设置当前 Windows 用户 SID 的独占文件 ACL；非敏感 `search-link.json` 固定 `enabled=false`。两者留在 ignored `.runtime/baichuan-ai-local`，拒绝符号链接、Windows reparse 路径、不明所属环境及任何已有配置覆盖；保留原密钥文件。不要把私有凭据文件提交、截图或复制到证据。

这一步不代表搜索质量通过。没有 activate 子命令，不接入 `local_dev`，不重启，也不启用研究或事实写入。为后续集成预留的 `backend_search_environment(service)` 只接受 `portal` / `baichuan-worker`，目前始终返回 `PRODUCT_WEB_SEARCH_ENABLED=false`，不读取或释放密钥。provider 和 token-env 名称准确复用现有后端 `TAVILY_API_KEY` / `BRAVE_API_KEY` 契约；不得将密钥放入 frontend、通用 gateway 或 model-gateway 环境。真实质量验证及门禁实现仍需后续独立完成。

纯临时目录检查：

```powershell
& '.runtime/company-test/python/Scripts/python.exe' -m unittest discover -s scripts/baichuan/tests -p test_local_search.py -v
```

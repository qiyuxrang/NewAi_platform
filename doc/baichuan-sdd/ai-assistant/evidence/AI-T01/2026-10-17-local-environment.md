# AI-T01 本机恢复与隔离开发入口（2026-10-17）

环境：Windows / PowerShell，仓库 `C:/Users/YLJJT/Desktop/NewAi_platform-main`，HEAD `ef1676cd8327d693dab897c45a234ba91413884e`。本轮用户授权本地启动、开发和隔离验证，不含远程生产修改。

当前补充状态：用户提供原 Excel 后，已在保留本地账号、权限和会话的同一 owned 库接入源表，实查 1283 家。页面标识“本地源表资料，历史官网补查未恢复”，`dataset_kind=isolation / source_kind=local_original_excel / local_source_only=true`。下文初始空库与未定位原件的记录保留其原执行时间；当前源表基线与非空验证见文末。历史官网研究数据库及其补查成果仍未恢复。

## 实际发现

- 原入口 `启动项目.cmd` 调用 `scripts/start-enterprise.ps1`，文档地址为 `http://127.0.0.1:3080/departments/product/baichuan`。本机没有 `.env`、`.runtime/enterprise`、Docker CLI/Docker Desktop 及其原数据卷；启动必需的原私有配置与打包运行路径也未迁入。本轮没有创建假正式 `.env` 或重建原数据卷。
- 本机 `C:/Users` 只有 Public/YLJJT，历史记录的 `C:/Users/BJRunner/.agent-reach/...` 无法在当前机器定位。旧 Excel 和网页研究原件未确认；历史 1283 家不作为当前准确总数。
- 只读枚举 `.runtime` 与 `services/business/.runtime` 的 SQLite 文件，排除依赖目录、工程价格缓存和明确的备份路径测试：共 42 个 SQLite 文件，仅本轮新建隔离库含 `portal_company`。旧 `.runtime/company-trial/portal.sqlite3` 停留在 portal 0035，尚无公司/资质/人员表；它不能提供真实企业基线。盘点结果在 ignored `.runtime/baichuan-ai-local/sqlite-discovery.json`。
- 真实库的当前企业、资质、人员数量与字段核实覆盖均为 **未确认**。AI-T01 的真实数据基线仍未完成。

## Excel 来源补充核查

本轮按 spreadsheets 技能执行只读 ZIP/XML 元数据核查，未编辑或另存原工作簿。`doc/baichuan-sdd/assets/initial-template.xlsx` 为 14,382 字节，SHA-256 `68bc45a0063886d99d3964ffea0a47aa45f8a88a3d5b8fe687173826722bddad`：企业资料页仅 1 行表头、核心人员页仅 1 行表头、填写说明页 22 个非空行。它是空模板，不能恢复既有企业。

在 `output`、`.runtime`、`doc/baichuan-sdd/assets` 范围，排除 Python/Node 依赖目录，对 210 个 `.xlsx/.xls/.csv/.tsv` 文件读取文件哈希，对 XLSX 读取工作表名与非空行数；没有输出企业、人员、联系方式等单元格内容。历史源文件 SHA 前缀 `220ec` 匹配数为 0。表名含百川/企业资料/资质的候选只有上述空模板；五份通用 UUID 命名 source 附件均为同一 4,043 字节产品合成样例指纹 `344e0680aec6601038f0af8ec0ac07c4c547ad82bfac5d7ce2800c1056b0e522`，未被当成百川来源。脱敏工作簿元数据与清单分别存于 ignored `all-workbook-metadata.json` / `source-workbook-discovery.json`。上述范围内未定位旧百川 Excel 整理成果；不据此否定历史成果的存在。

## 已交付本地入口

补充只读定位：在用户 Desktop、Documents、Downloads、OneDrive 使用 `rg --files --hidden` 枚举路径，排除本工程后按“百川/baichuan/企业资料/企业资质/MultiUserClaw”名称及数据文件扩展名核查，四目录命名候选均为 0。只统计路径，不读取或展示个人文件内容；这不证明所有非标准名称文件均无原数据。

- 新增 `scripts/baichuan/local_dev.py`，专用 `.runtime/baichuan-ai-local`，不复制试运行业务数据，仅增量 migrate、幂等 seed_portal 和两类专用开发账号。实际迁移已应用到 `0046_baichuan_assistant_foundation`。
- 本地页面：`http://127.0.0.1:13180/departments/product/baichuan`。Django `18100`、网关 `18080`、Vite `13180` 均绑定 `127.0.0.1`。
- `scripts/baichuan/local_frontend.mjs` 在开发服务器页面显著注入“隔离开发库，尚未连接现有企业资料”。该提示不进入正式构建。
- 私有凭据 `.runtime/baichuan-ai-local/accounts.json` / `secrets.json` 均通过 git check-ignore，Windows ACL 仅授予当前用户；不输出凭据内容，不重置已创建账号密码。
- `start/status/stop/migrate` 使用所有权标记、串行 helper 文件锁、进程创建时间/可执行路径/命令身份验证。被无主进程占用的端口拒绝复用；停止仅针对本启动器仍可证明归属的进程。关闭与刷新不会删除数据库。
- 新增 `scripts/baichuan/inventory_sqlite.py`：显式现有文件、SQLite URI `mode=ro`、`query_only=ON`，仅输出数量、非空覆盖和文件指纹；缺表输出 null，不误报为空正式库。非空不等于事实核实。

## 本轮实际检查

1. `python scripts/baichuan/local_dev.py start`：全量迁移至当前叶节点成功，健康地址均 HTTP 200。新隔离库企业/资质/人员均 0。
2. HTTP 页面与 API：页面 200 且隔离提示存在；未登录企业列表 401。专用 product、general_manager 各完成真实 HTTP 登录/企业会话绑定/列表请求，均 200，total=0。记录 `.runtime/baichuan-ai-local/http-verification.json`。这不是实际企业或真实业务账号验收。
3. 重复 start：退出码 0，三进程的 PID/创建时间/可执行程序/命令身份完全不变；原试运行双库与本地凭据哈希不变。记录 `.runtime/baichuan-ai-local/repeat-start-verification.json`。
4. 原试运行 portal SHA-256：`bf63801cacaede1ac58a476c0e541ecd55cca222d5af992858ad5d409ac8f5f3`；platform：`47bc0cfabd23fb94bdf6bd19a5484d15bfe946a7f2f3e870e20f351e51a88301`。隔离启动、登录与重复启动没有写入这两个既有库。
5. Python py_compile、Node `--check` 与 `git diff --check` 实际通过。未把本地空库 HTTP 验证升级为 AI-AC18 或真实全库验收。

## 恢复与限制

使用 `.runtime/company-test/python/Scripts/python.exe scripts/baichuan/local_dev.py status` 查看进程；`start` 重复可用，`stop` 仅停止所属进程。后端目前使用 `--noreload`；服务端代码变更后需 stop/start，持久库保留并增量迁移。

接下来可继续本地助手、规则、任务底座和集成验证。真实企业清单、全库研究与生产迁移须先找到原业务数据库/备份与研究原件，并完成只读基线和备份验证。本轮没有向远程生产、原试运行库或任何全库资料写入事实。

## 既有模型配置复用补充

只读检查原 `.runtime/company-trial/model.env` 的存在与配置键，并依据原 `scripts/company-trial.py` 的 `model_configuration()` 读取现成上游配置；未输出配置值或密钥。新增 `scripts/baichuan/local_model.py configure/probe/activate`，只在 owned 隔离库创建独立 Provider/Model 与标准 `product_assistant` 业务路由，不修改原 trial 库/文件，不扩充账号角色授权。上游密钥仅注入新 owned 模型网关的进程环境，未进入命令行、证据或受版本管理文件。私有配置标记和内部服务令牌保存在 ignored/ACL 受限目录。

独立模型网关绑定 `127.0.0.1:18412`，复用普通业务鉴权与调用日志；真实一次有界合成探测成功后，完成文字+合成 DOCX 的真实浏览器模型链路，详细成功/失败与修复证据见 AI-T13 同日记录。最终 `status` 验证 model-gateway、portal、gateway、baichuan-worker、frontend 五进程均 `owned_running=true`。原 trial 双库最终 SHA-256 与前述指纹一致；真实企业源仍未连接，本地企业保持 0。

搜索检查仅报告可用性：进程缺 Tavily/Brave/SEARXNG 配置；既有 generated.env 无相应搜索键，独立搜索配置不存在且 Docker 不可用。模型复用不等于搜索可用，当前搜索能力仍为 false。数据库、运行数据和调用日志均限于专用本地环境。

最终后端文件取消/多轮去重与重试计数业务代码冻结后，仅执行 owned `stop` / `start` 加载最新 portal/worker，未重跑模型请求。四健康地址均 HTTP 200，五服务 `owned_running=true`，增量迁移无待执行项、账号密码保留；只读最终收据再次确认本地企业数 0、原 trial portal/platform SHA-256 与初始值完全一致。脱敏收据保存在 ignored `final-restart-receipt.json`。

最终冻结复核（2026-10-17T18:54:18.792019+08:00）：旧重启收据早于最终 service/worker 修改，已再次仅对 owned 五服务 stop/start，加载待附件续接、文件取消与导出失败回复修复后的最终代码。四健康均 200、五服务归属确认、本地公司 0、原 trial 双库指纹不变；本次未增加模型调用。最终收据 `final-restart-receipt.json` 记录完成时间与 service/conditions/file_conditions/worker 的修改时间、SHA-256，可核对已加载版本。此前真实合成模型链路证据保留，最终新增后端修复由隔离后端测试验证，未冒充新增真实企业浏览器验收。

## 用户原源表接入后的本地基线与运行复核

2026-10-17 19:24:15 +08:00 完成源表标签同步与非空浏览器验证。此前空库收据已由最新 `final-restart-receipt.json` 替换，其当前 `source_connected=true / local_source_only=true / historical_enrichment_restored=false / dataset_kind=isolation`；不表示找回旧正式库或历史官网研究。

- 用户微信目录原件与 owned `source-restore-220ec53e/original.xlsx` 分别只读 SHA-256，均为 `220ec53ebe6a87263978f297891107700070d07588a4532b62ba884d64f68f07`，原件未变。
- 源表接入后直接只读聚合：1283 企业、1460 资质声明、1024 家电话非空、0 人员、0 官网。非空及原表声明不等于当前事实核实；原 1462 行声明保留情况、幂等导入与两条未分类 CCRC 的证据由源表恢复执行单元单列，不以当前结构化数量掩盖未解析项。
- 导入前本地备份与当前库逐项比较：原用户密码及角色关联不变，原会话 ID 全部保留；当前会话 9（原 7，加两角色明确标注的确定规则验收会话），角色关联 2，SQLite quick_check=ok。
- 只停止并启动可证明归属的五服务，标签同步到 portal API、Vite 页面及启动器状态；四健康地址实际 HTTP 200、五服务 `owned_running=true`。旧 trial portal/platform SHA-256 仍为本记录初始值，未写入原试运行库。
- 新增来源状态兼容逻辑和 4 项临时目录测试实际通过：无/坏/未完成收据不宣告连接；只有本地源表类型、完成标记、合法 SHA、正整数数量且历史未恢复时显示本地来源标签。不会通过切换标签改变数据库路径、账号或权限。
- 两角色非空浏览器、源表行级来源、精确筛选、确定规则候选快照与受控 Excel 结果详见 AI-T13 同日补充。该验证模型调用增量 0、浏览器非 loopback 请求 0。截图与 JSON 保存在 ignored `source-browser-verification/`，未上传业务资料。

最新运行收据：`.runtime/baichuan-ai-local/final-restart-receipt.json`，完成时间 `2026-10-17T11:24:15.697182+00:00`。随后规则维护入口安装版本规则如由主执行单元完成，将单列维护证据；既有固定快照与截图保留其安装前的真实状态，不反向修改。

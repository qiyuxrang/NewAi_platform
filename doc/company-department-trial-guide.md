# 公司部门试用说明

本轮准备了 20 份合成输入材料、工程六表成果和已有三件套渲染样本。所有身份、项目、价格、定额及简历都用于测试。已接通真实 `qwen3.8-flash`，三部门问答和人事模型业务通过真实 HTTP 验证；完整长文三件套与云端生产运行尚未最终验收。本轮优先稳定后端，前端优化暂缓，另一台电脑的 RAGFlow 暂不接入。

## 当前本机入口

- 员工工作台：http://127.0.0.1:13180
- 平台管理：http://127.0.0.1:13181
- 原业务管理：http://127.0.0.1:18100/admin/
- 账号文件：`.runtime/company-trial/accounts.json`。包含产品、人事、工程、总经理和管理员五个随机密码账号，只在本机查阅。
- 输入目录：`.runtime/company-trial/materials/`。
- 独立模型网关：http://127.0.0.1:18410。当前试用共 8 个服务，启动脚本会自动启动模型网关、工程、人事和产品 Worker。

登录相应部门账号。若提示业务账号未连接，进入“设置→业务账号”，使用同一试用账号和密码连接。后台状态提示“服务初始化中”来自本机未启动的 OpenClaw 员工容器；此试用环境使用真实部门接口、隔离 SQLite，并不创建 Docker 员工容器。

## 产品事业部

1. 使用 `trial-product`，进入“新建项目”。
2. 设备清单选 `materials/engineering/设备清单_合成测试.xlsx`；项目背景选同目录 `项目背景_测试.txt`。
3. 点击“上传并保存资料”，核对新项目、2 份原始资料、解析状态和输入版本；从历史重新打开。
4. 补充资料后核对版本变化及旧内容失效；跨部门账号不应访问该项目。
5. 当前真实模型已配置，后台产品 Worker 支持 `source_only_preview`：仅依据上传资料生成预览，不使用 RAGFlow，不伪造知识库来源。完整三件套长文尚未验收，技术方案 50000 字、可研 70000 字门槛保留，正式发布关闭。已有 Office 样本位于测试包 `samples/三件套测试样本.zip`，仅用于查看排版与编辑能力，不代表本次真实 AI 完整三件套生成完成。

## 工程部

1. 使用 `trial-engineering`，进入“报价分析”。
2. 同时选设备和劳务两个合成 XLSX，地区可留空默认陕西；点击“创建内部成本草稿”。
3. 工程 Worker 自动领取任务，刷新或等待状态变为“已完成”；打开该任务，下载 ZIP。
4. ZIP 包含两本 XLSX，每本 6 个表；核对数量、合成价格、取费与汇总、甲供及暂估提示。设备的“可疑”健康结论反映实际暂估，不应直接用于采购报价。
5. 上传 `负数量_拒绝样本.xlsx` 应拒绝；`重复行_警告样本.xlsx` 应提示预检问题。输出六表不得重新充当原始清单。
6. 换人事账号访问工程任务应拒绝。试用数据仅在 `engineering-data/`，不覆盖业务默认价格库。

## 人事部

1. 使用 `trial-hr`，在 JD 对话框粘贴 `materials/hr/synthetic-jd-data-engineer.txt`，点击“生成通用 JD”，人工检查并确认后再进行 BOSS 适配。真实模型的生成、人工确认和适配已通过 HTTP 验证；模型接通后尚未重新完成整套网页验收。
2. “简历筛选”页面支持上传 JD 的 TXT/DOCX/PDF，并上传高匹配 DOCX、同内容 PDF、低匹配 TXT、缺项 TXT、扫描 PDF 五种简历。真实模型 Worker 的独立复跑已完成 DOCX、TXT、扫描 PDF 三份简历处理；第一次扫描 PDF 曾出现 `vision_review_required`，独立视觉复测成功，第二次整批运行三份均成功且未用 retry。该样本结果不代表扫描件普遍稳定；本地 RapidOCR 安装问题仍待解决。
3. 人工文件提取、JD 确认、上传、历史、规则得分和 CSV 的历史 API 证据在测试包 `hr/`；新真实模型业务、CSV 和越权证据见 `.runtime/company-test/core/real-model-business/results.json`，共 35/35 通过。可按验收脚本用新的独立数据库复跑。
4. 手工转正链路已通过创建→收集→提交主管→主管批准→HR 归档。当前没有转正网页入口，按 `hr/人事部试用步骤.md` 的 API 部分测试。

人事文件上传在当前界面位于“简历筛选”，不在 JD 生成对话框。复跑脚本的账号、数据库与私有附件是独立测试环境，不能直接使用它的测试 ID 访问当前五账号试用库。模拟匹配输出文件名明确带 `protocol-fixture`，不得作为真实模型验收。

## 总经理、财务与管理员

- `trial-general_manager` 可以进入三部门工作台，但没有员工私有资料权限。经营/财务接口的完整正向和越权结果见 `management/`，不将三个部门入口认定为完整经营看板。
- 财务、售前、工程台账材料见 `materials/management/`，BIFF XLS 及标准化 CSV 见 `materials/workbooks/`。财务发布需对应业务授权，当前五账号网页试用未创建财务员工入口；使用管理验收脚本在独立库复跑。
- `trial-platform_admin` 登录 13181 管理应用，测试用户列表/部门分配、审计、用量、容器状态。当前容器状态未验证；若做改密/停用测试，旧登录凭据和活跃 WebSocket 应被撤销，复测时使用更新后的密码。

## 复现与停止

脚本和材料包需要与当前完整项目源码一起使用。Node 与 Python 依赖需先安装，测试包不携带 `node_modules` 或虚拟环境。Windows 完整 Python 环境可按 `deploy/cloud/requirements.lock` 安装，另装仅本机试用所需 `aiosqlite`；Windows 需要原生 Office 的检查另装 `pywin32`。Linux 生产使用 `deploy/cloud/`，不要使用此 SQLite 试用脚本代替部署。

当前已经准备好环境并配置真实模型，无需再次确认授权。仓库根目录执行：

```powershell
& .runtime/company-test/python/Scripts/python.exe scripts/company-trial.py status
& .runtime/company-test/python/Scripts/python.exe scripts/company-trial.py stop
& .runtime/company-test/python/Scripts/python.exe scripts/company-trial.py start
```

`stop` 只终止核验归属的试用进程，保留账号、数据库和材料；没有完成停止时不要重复 `start`。新机器首次使用：

```powershell
python scripts/company-trial.py prepare --python C:/absolute/path/python.exe --parser-python C:/absolute/path/python312.exe --node C:/absolute/path/node.exe
python scripts/company-trial.py materials
python scripts/company-trial.py start
```

`--parser-python` 为可选参数，只指定产品资料解析器使用的 Python；RapidOCR 1.4.4 需要 Python 3.13 以下，可为它单独安装 Python 3.12。业务及文档处理仍使用 `--python` 指定的解释器。省略该参数时，产品解析器继续使用业务解释器，旧版配置也按此默认值运行。路径会写入本机私有 `.runtime/company-trial/config.json` 的 `parser_python` 字段，且准备前会验证该解释器文件存在。

`prepare` 会拒绝重建已存在的试用配置或数据库，以保护现有账号和试用数据。因此，已经准备好的试用环境不能靠再次运行 `prepare --parser-python ...` 更新；由本机操作者只在私有 `config.json` 中添加或更新 `parser_python` 为 Python 3.12 的完整路径，保留其他字段，再按正常维护流程重启试用服务使新配置生效。此项不需要也不应提供模型密钥。

将测试包中 `payload/.runtime/company-test/` 还原到仓库同名目录后，`materials` 才能找到固定的合成来源。脚本拒绝覆盖已有试用账号及不同内容的同名材料。真实原始台账和生产数据库不属于此试用环境；本机私有模型凭据不属于可移交测试包。

## 私有模型配置与连接检查

本机私有文件 `.runtime/company-trial/model.env` 保存配置，不加入版本库或测试包。当前机器已经配置，不要用下方占位符覆盖现有密钥；新机器使用自己的密钥填写：

```dotenv
MODEL_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
MODEL_NAME=qwen3.8-flash
PORTAL_MODEL_KEY_PRIMARY=<填写本机私有API密钥>
MODEL_SUPPORTS_VISION=1
MODEL_MAX_OUTPUT_TOKENS=8192
MODEL_TIMEOUT_SECONDS=120
```

前三项必填；Base URL 必须为规范 HTTPS API 根地址，密钥不得包含空白。视觉开关只能为 `0` 或 `1`（默认 `0`），输出上限为 1–8192（默认 4096），超时为 1–600 秒（默认 120）。API 密钥只注入本机独立模型网关，不写入数据库或前端；数据库仅保存模型、路由、公开配置和密钥环境变量名称。

`prepare` 自动创建独立的私有模型网关服务令牌；当前本机也已配置。配置完成后在仓库根目录执行以下步骤。更新运行中的配置时先 stop，再 configure、start、probe；新机器需先完成上面的 prepare 和 materials：

```powershell
& .runtime/company-test/python/Scripts/python.exe scripts/company-trial.py stop
& .runtime/company-test/python/Scripts/python.exe scripts/company-model.py configure
& .runtime/company-test/python/Scripts/python.exe scripts/company-trial.py start
& .runtime/company-test/python/Scripts/python.exe scripts/company-model.py probe
& .runtime/company-test/python/Scripts/python.exe scripts/company-trial.py status
```

`configure` 配置产品、人事、工程共 10 条模型路由；`probe` 成功应返回 `status: success`、`code: ok`，只报告状态、用量和耗时，不显示密钥或上游响应正文。当前接通与验证详情见 [后端模型接入报告](backend-model-connection-20261011.md)。

## 公司测试记录

全业务复跑：`python scripts/run-department-regression.py --parallel 4`。需先安装测试依赖 `tblib`；脚本生成新的独立目录、数据库和随机测试 secret，记录命令与退出码，不输出 secret。它覆盖 Django、平台及部署结构；浏览器、Office、真实模型和目标 Linux 验收另按报告执行。

按部门记录：操作者、材料文件名、步骤、预期、实际、任务/版本、下载文件哈希、问题截图和复测结论。合成材料不足时，可增加带“合成测试”标签的新样本；真实模型 HTTP 验证已完成，网页复验、完整三件套及目标云环境仍须分别用相同业务路径验收。最终待验收项见 `company-department-test-report-20261011.md`。

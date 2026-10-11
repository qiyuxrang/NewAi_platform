# 公司各部门业务测试报告

日期：2026-10-11。结论：基础业务、权限隔离与合成材料试用已具备测试条件；真实 `qwen3.8-flash` 的三部门问答和人事业务已通过真实 HTTP 验证。完整长文三件套、扫描件普遍稳定性与 Linux Docker 生产运行尚未达到最终验收标准。所有样本为自行制作并标注的合成资料，没有使用真实候选人或公司财务数据。本轮优先稳定后端，前端优化暂缓，RAGFlow 在另一台电脑暂不接入。

## 已执行的检查

| 范围 | 已验证结果与边界 | 证据 |
| --- | --- | --- |
| 历史全业务 Django 回归 | 执行 1244 项，1218 通过，26 跳过，0 失败、0 错误；后续源码有修改，不作为当前源码验收 | `.runtime/company-test/core/django-full-integrated.log` |
| 结构化输出调用链专项 | 主代理网关72项、门户网关41项全部通过；Worker与质量最新组合242项通过，运行前后源码摘要一致。与业务和产品套件重叠，不叠加计数；此项不代表完整三件套通过 | `core/model-json-contract-parent/parent01/result.json`、`core/product-quality-parent/structured-localfields-parent03-result.json` |
| 当前供应商结构化格式实测 | 第四周期第六轮两次正常调用均返回完整结构，随后因内容问题被阻断；FAILED49、累计29派发、实际正文19451字、无可研/PPT/最终文件。格式能力已实测，成果验收尚未通过 | `core/real-model-web-triad-quality-v4/attempt-budget-v48.json`、`attempt-budget-v49.json` |
| 后续冻结源码阶段回归 | 业务1502项：1478通过、24跳过；平台47/47、云包静态与模拟检查7/7；源码前后SHA一致。后续仍修复生成质量，不作为最终交付源码验收 | `.runtime/department-regression-20261012-032238-f88c12/source-evidence.json` |
| 同期产品全量阶段回归 | 606项：604通过、2跳过，源码前后SHA一致；与业务回归重叠，后续修改后须重新核验 | `core/product-quality-parent/full11-result.json` |
| 第四周期修复前全业务阶段回归 | 业务1530项：1506通过、24跳过；平台47/47、云部署包8/8，运行前后源码SHA一致。后续正文质量规则仍有必要修复，此记录保留为阶段基线 | `.runtime/department-regression-20261012-045752-b20503/source-evidence.json` |
| 第四周期修复前产品完整回归 | 634项：632通过、2跳过，运行前后源码SHA一致；与全业务套件重叠，不累计计数。不能替代真实文章验收 | `core/product-quality-parent/full12-result.json` |
| 平台认证、管理员、代理及活跃 WebSocket 撤权 | 47/47 通过，最终独立复跑 | `core/platform-integrated-final.log` |
| Linux 部署包结构、配置与模拟备份异常 | 7/7 通过；没有实际运行 Docker | `core/cloud-package-integrated-final.log` |
| 人事专项 | 106 通过、1 PostgreSQL 跳过；81/81 API 检查，29/29 试用数据检查 | `hr/report.json`、`hr/evidence/checks.json` |
| 工程专项 | 51/51 回归，74/74 API→实际 Worker→CLI→六表检查，8/8 CLI 自检 | `engineering/acceptance.json`、`engineering/logs/final-tests.txt` |
| 财务、总经理与管理业务 | 143/143 回归，125/125 真实 HTTP，7/7 BIFF XLS 检查 | `management/management-summary.json`、`management/http-20261011-153940/results.json` |
| 员工及管理网页（模型接通前） | 39/39 真实浏览器检查通过，0 页面异常；产品上传、工程计算与下载、人事无授权模型拒绝；不代表模型接通后网页重验 | `core/browser/results.json` |
| 前端构建 | 员工 TypeScript/Vite 与管理 Next.js 生产构建通过 | `core/frontend-build-integrated-final.log`、`core/manage-build-final.log` |
| 公司业务前端 lint | 0 错误、4 个 React Hook 警告 | `core/company-frontend-lint-final.log` |
| Office 实际打开与渲染 | 人事 2 份 DOCX 共 2 页；工程 2 份 XLSX 共 12 个工作表/12 页；源文件不变 | `core/native-hr-*-01/report.json`、`core/native-engineering-*-02/report.json` |
| 真实模型业务 HTTP | 35/35 通过：三部门问答、HR JD 生成/人工确认/BOSS 适配、DOCX/TXT/扫描 PDF 三份简历的真实 Worker、CSV 和越权；没有响应替身，没有 RAG | `.runtime/company-test/core/real-model-business/results.json` |
| 产品真实蓝图 | 8/8：创建、排队、真实 Worker/千问、蓝图保存并停在人工确认；首次条件校验失败已修复，保留失败记录 | `.runtime/company-test/core/real-model-product/results.json`，详见后端接入报告 |
| 模型配置与隔离检查 | 配置测试 9/9、模型 CLI 9/9、模型网关 65/65 通过 | [后端模型接入报告](backend-model-connection-20261011.md)中的命令与证据 |

专项回归与全业务回归存在重叠，不能把各行相加作为独立测试总数。人事 81 项包含明确标注的模型协议替身检查：真实文件解析、规则评分、租约、持久化和权限接口实际执行，模型返回内容使用 `protocol_fixture_not_llm`，不代表真实 AI 已通过。管理 HTTP 使用真实服务器和文件 SQLite，但不运行要求 PostgreSQL/Docker 的生产 lifespan。浏览器使用实际接口，没有拦截并伪造成功响应。

新增 35 项使用真实 `qwen3.8-flash`，与历史协议替身证据分开记录。第一次扫描 PDF 曾出现 `vision_review_required`；独立视觉复测成功，第二次整批独立运行三份简历均成功，第二轮未使用 retry。该结果仅证明本轮样本的真实模型视觉路径成功，不证明扫描件普遍稳定，也不证明本地 RapidOCR 安装成功。

当前标准北京 Base URL 为 `https://dashscope.aliyuncs.com/compatible-mode/v1`，产品、人事、工程共配置 10 条路由。API 密钥只交给本机 18410 独立模型网关，不落数据库、前端或测试包；试用启动脚本自动启动模型网关、人事和产品 Worker，连同已有服务共 8 个服务。配置、probe 和详细证据见 [后端模型接入报告](backend-model-connection-20261011.md)及试用指南。

全量回归的 26 个跳过项逐项保留在日志：PostgreSQL 原生池/并发/行锁和生产导入边界、Linux 原生进程隔离、Windows 符号链接权限、直接运行的 OOXML 检查的委托入口，以及根全量执行未配置的两个工程 CLI 项。两个 CLI 项已在工程专项中实际通过；OOXML 检查主体在全量中直接执行。不得把数据库并发跳过项改算为成功。

后续自包含阶段回归已为工程CLI提供合成价格库材料，相关项目在全量中实际执行。该轮24个跳过项分别为21个真实PostgreSQL检查、1个Linux原生pidfd隔离检查、1个Windows符号链接权限检查，以及1个委托Office安全检查入口；Office安全检查主体已直接运行，不能把重复委托入口当作额外独立验证。环境专属项目仍须目标环境验证。

## 各部门可测试的业务

2026年10月12日阶段冻结回归：产品全量664项（662通过、2跳过）；部门业务1572项（1548通过、24跳过）、平台47项、模型网关80项、部署包8项均无失败，各轮执行前后源码摘要一致。证据为`core/product-quality-parent/full15-result.json`及`.runtime/department-regression-20261012-063704-aa52ac/`。这些结果对应当轮源码，随后因真实生成发现的计数及正文合同问题继续修改，不能代替修改后的最终冻结回归或实际三件套验收。

| 部门或角色 | 本轮测试范围 | 当前试用边界 |
| --- | --- | --- |
| 产品事业部 | 新建、原始资料上传与解析、版本冲突、幂等、审批、草稿/成果下载、授权预览、撤权、跨账号隔离、商机和三件套质量门槛；新增真实部门问答 | 网页可保存设备 XLSX+背景 TXT；真实模型已接通，后台支持 source_only_preview；RAGFlow 暂搁，完整三件套长文生成未通过，正式发布关闭 |
| 人事部 | JD 原始文件提取和确认、需求版本、5 份简历上传、匹配规则、UNKNOWN、证据校验、CSV、历史、撤权、手工转正审批归档；新增真实 JD/BOSS 适配及三份简历 Worker | 真实模型 HTTP 和本轮扫描 PDF 视觉样本通过；HR 视觉路径与产品解析器 RapidOCR 分开验证，扫描 JD 仍按现有政策拒绝；模型接通后网页尚未重验；转正仅 API，无网页入口 |
| 工程部 | 双清单上传、预检、成本引擎、取价和取费复算、甲供、纯劳务、真实后台领取任务、六表 XLSX/ZIP、重试、原始及成果哈希校验、权限隔离 | 网页完整计算下载已通过；合成价和定额用于试用，暂估须询价，离线六表未应用地区系数；输出为计算值，无 Excel 公式 |
| 财务台账 | 合成 CSV/XLS 解析、暂存、校验、版本冲突、本人发布和权限边界 | API 可测；当前员工工作台无独立财务入口，平台部门枚举也未包含财务，不作为网页财务功能交付 |
| 总经理 | 三部门台账、来源引用、读取时权限复核、统计和经营相关 API、私有资料隔离 | 网页现有三部门入口；经营看板不完整，财务员工专属入口禁止经理绕过 |
| 平台管理员 | 五类业务分配、登录/改密/重置、首次改密、审计、用量、分页、容器状态和 WebSocket 撤权 | 管理网页五个页面已实际访问；没有 Docker 的状态明确未验证，不能据此认定真实容器运行正常 |

“售前”样本用于现有售前/商机/台账业务接口验证；现有员工部门导航只有产品、人事、工程三个，不将不存在的独立售前网页计作完成。

## 修复与整合

- 修复工程合法 XLSX 缺失 dimension 时崩溃，限制读取上限；隔离试用价格、定额、缓存和成果目录；修正暂估健康提示、甲供零价、纯劳务分类、地区传递和说明行裁切。
- 修复密码变化后旧 access/refresh/API token 仍可用；活跃 WebSocket 每 5 秒及每条消息前复核，停用、改密、管理员降权和身份库故障关闭连接。
- 限制 bcrypt 输入字节和分页范围；容器用量只统计已登记容器，不用历史状态代替真实状态。
- 修复总经理访问财务员工入口的权限旁路，保留三部门经理导航；补齐遗漏的验证工具及隔离的历史测试 fixture。
- 补齐原生 PDF、Agent 依赖；升级 DRF 到 3.18.3，并通过请求大小和 AdminRenderer 权限回归。上游依据：[DRF 发布记录](https://www.django-rest-framework.org/community/release-notes/)。
- 修复产品切换项目/资料版本时旧响应或纠正内容遗留；公司业务前端 lint 清零错误；管理链接按部署域名构建。
- 提供独立试用脚本，随机私有账号，真实身份桥接，自动启动工程 Worker；启动异常清理仅处理本次拥有的进程，停止时核对进程创建时间、可执行文件和完整命令。
- 接通私有配置的真实模型，配置三部门 10 条路由并自动启动独立模型网关、人事和产品 Worker；保留 source_only_preview、长文质量门槛与关闭正式发布的边界。

## 尚未通过的最终验收项

1. **真实三件套稳定生成**：真实模型已接通，后台支持仅依据上传资料的 `source_only_preview`；RAGFlow 暂不接入，不伪造知识库来源，正式发布关闭。已有三件套 Office 样本仅说明文档渲染/排版链路；短正文未达到技术方案 50000 字、可研 70000 字，被质量门槛拒绝，未伪报正式完成。第四周期第三次尝试保存两章技术正文13823字后失败；独立通读发现真实概念与阈值错误，已通过正常版本接口修正12处，修正后实际正文14383字，仍没有完整可研、PPT和最终三份文件。具体原文、修正和阶段失败记录见联网生成报告。完整长文三件套仍需实际生成、全文与来源复核及全页排版验收。
2. **扫描件/图片在目标环境的稳定性**：历史 Python 3.13 安装 `rapidocr-onnxruntime==1.4.4` 被拒绝，证据 `core/ocr-install.log` 保留。现已在独立 Windows Python 3.12 环境按解析器锁定依赖实际识别一份 PNG 和一份无文本层 PDF，中英文数字均成功，缺依赖环境按预期拒绝；真实解析子进程的原有 Python socket 禁用也已验证。云候选包改用隔离的 Python 3.12 解析器，主业务解释器继续使用 3.13。当前本机试用也已单独配置该解析器，并经正常认证业务 API 实际上传 PNG/PDF，两份均返回 OCR 文本和 `needs_review`，没有调用模型或 RAGFlow。证据 `cloud-ocr/evidence/verification.json`、`core/ocr-parent/real-parser-final-01-result.json`、`core/ocr-parent/portal-upload-final-01.json`。该成功不证明所有扫描件准确，不代表 Linux 容器实测或操作系统网络隔离通过。OCR 提取内容仍须人工核对。HR 使用独立模型视觉路径；扫描 JD 的拒绝政策没有改变。
3. **Linux Docker/PostgreSQL**：服务器未准备，本机无 Docker/WSL/真实 PostgreSQL；镜像构建、Linux Writer/Impress、数据库并发、TLS、真实一致备份恢复和重启持久化仍须目标环境验收。
4. **网页业务缺口与模型接通后复验**：财务台账、转正审批、完整经营看板没有对应完整网页流程，现有 API 测试不代替网页交付。历史 39 项浏览器检查发生在模型接通前；本次未重新验收模型生成的完整网页流程。用户明确前端暂缓，本轮不修复上述网页缺口。
5. **历史全站前端 lint**：公司业务范围无错误，但 OpenClaw 通用区域仍有 77 个既有错误及 8 个警告；本轮不将全站 lint 标为通过。前端生产构建存在主包超过 500 kB 的提示。

## 交付物

- `doc/company-department-trial-guide.md`：当前地址、账号位置、材料和操作步骤。
- `doc/backend-model-connection-20261011.md`：真实模型配置、密钥隔离、probe、真实 HTTP 业务和复测证据。
- 最终验收后生成 `.runtime/company-test/公司各部门测试包.zip`：汇集合成材料、实际成果、报告、执行日志、试用脚本和可复跑检查；与现有项目源码一起使用。当前尚未完成最终打包。
- 最终打包同时生成 `.runtime/company-test/交付清单.json`：记录文件哈希和实际测试状态；不以历史清单代替当前交付。
- `deploy/cloud/`：更新后的 Linux Docker 部署候选包；操作见 `deploy/cloud/README.md`。

测试包不包含私有凭据、数据库、上传存储或虚拟环境。当前私有试用账号仅保留在本机 `.runtime/company-trial/accounts.json`。部署最终标准仍见 `doc/cloud-product-delivery-standard.md`。

# 百川阁交付记录

2026-10-16，SDD V1.6最终追加结果：全部1283家已完成一轮公开资料核对，114家接入484条原页支持事实，实际新增/补充251个公司业务字段及13条人员。当前官网87家、电话1026家、人员125条关联91家。全部企业统一官网入口；1196家官网仍缺明确来源，按钮禁用。实际新增官网、人员及两工作台页面验证通过。详细改动、检查、截图、剩余依赖见[全库补查交付记录](enrichment-delivery.md)。下方V1.5“正在执行”和33官网属于历史阶段。

2026-10-16，SDD V1.5追加结果优先：全部1283家共用详情顶部“访问企业官网”入口；有地址安全新标签，无地址禁用并向维护者提供现有添加入口。定向19/19、类型/局部Lint/Vite、隔离浏览器14组、真实双工作台8组布局+4组行为通过；全部1283投影分别渲染维护/只读分支通过。证据为evidence/official-button系列，最终截图在私人official-button-evidence目录。当前33家有官网，1250家待补查；万邦定向检索没有确认官网，不猜填。旧段落“无官网不显示入口”已由FR-25覆盖。

用户要求全部企业，T-27/AC-30正在进行：1283家分批补查，研究覆盖、已接受事实和页面实际保存分别统计，不能把检索台账当作资料完整。此前前端全套84/85的任务外失败及T-17未关闭状态保留。

2026-10-16，SDD V1.4，当前工作区未提交。用户要求严格遵循第一张详情图，本轮已更新至现有3080平台，最新结果优先于下方历史记录。

## 本轮严格视觉对齐

详情共用顶部企业展示卡、参考建筑装饰、右侧官网、两行约3:2卡片网格、圆形渐变图标、英文副标和业务图片卡。板块按行对齐，单项或奇数末项资质占满该栏；安防采用参考绿色，官网主按钮深蓝，业务正文浅蓝渐变背景。企业标题32/38px、板块24px、正文16px保留。已实测凯笙及资料较少的万邦，两工作台均使用同一详情组件，没有退回纵向全宽卡片。

参考图归档于[detail-reference.png](assets/detail-reference.png)。本地建筑/业务图取自用户参考图的无文字区域，作为装饰；凯笙标识仅绑定名称完全相符的凯笙公司，其他公司为中性标识。图片不声称是各公司实景；没有复制示例的高新身份、额外资质、业务或定位。未修改真实公司资料、授权、数据库结构或运行进程。

实际文件：frontend/src/business/product/CompanyDetail.tsx、Baichuan.css、assets/baichuan/下8张PNG和source.json；frontend/tests/baichuan.test.mjs及baichuan-browser.py（官网按钮名称同步）；SDD规格/方案/任务/验收及本轮证据。没有增加依赖。当前文件指纹见[实现版本](evidence/strict-style-implementation-version.json)。

| 实际执行检查 | 结果 | 证据 |
| --- | --- | --- |
| 百川阁前端定向 | 18/18 PASS | [日志](evidence/strict-style-frontend-tests.txt) |
| TypeScript/局部ESLint/Vite构建 | PASS；既有大包提示保留 | [构建](evidence/strict-style-build.txt) |
| 隔离真实浏览器回归 | 14组PASS，含多等级、筛选组合、返回恢复、官网、编辑失败保留、版本冲突 | [日志](evidence/strict-style-browser-regression.txt)、[结果](evidence/strict-style-isolated-results.json) |
| 本机真实账号与页面 | 总经理/产品×凯笙/万邦×1440/1920，8组布局和4组行为PASS；无API替代或真实公司写入 | [结果](evidence/strict-style-live-results.json) |

主代理实际查看最终截图，确认图片正常、标题和正文可读、英文副标显示、两栏行对齐、无横向溢出、固定外壳仅正文滚动。公司资质/人员行数与真实API一致；万邦无官网和业务时隐藏相应入口/模块。凯笙官网实际打开新标签，剪贴板成功与注入拒绝结果正确；来源和返回URL恢复通过，pageerror为空。

截图目录：C:/Users/BJRunner/.agent-reach/baichuan-20261016/strict-style-evidence/。每个账号分别有ksznkj/wanbang的1440/1920及lower截图，前缀manager_user或product_user；共16张最终截图。只读验收脚本verify-strict-style.py和日志strict-style-run.txt同在私人工作目录，真实资料截图不提交Git。

本轮后端逻辑未变，没有重复执行后端测试或无关业务全套。此前后端27/27与资料保留证据见V1.3；此前全套前端84/85的任务外进度断言失败仍保留，不声称本轮全套通过。T-25/AC-28完成，T-17全站人工回归仍未完成；资料覆盖不足、证书时效/主体/任职事实核实等依赖保持下文记录，不能把样式调整视为事实核实完成。

## V1.3页面交付记录（历史）

2026-10-16，SDD V1.3，当前工作区未提交。最新结果优先于下方V1.2历史记录。

## 本轮截图调整及字体交付

已按用户最新列表与详情参考图更新两个现有工作台。公司列表名称22px；详情企业标题1440宽为32px、1920宽为38px，板块标题24px，正文、资质、业务及联系方式16px，标签14px。官网区加宽，网址完整单行。真实3080页面最终字体4组检查通过，无横向溢出。

详情改为企业展示卡、右上官网入口与复制、概览/业务和核心资质/联系方式双栏。只展示已填业务字段，统一社会信用代码、核实日期、系统时间及缺项占位不在默认内容中；来源原文仍可折叠展开。中性图标代替无依据的Logo，业务领域仅取明确录入内容。列表加入真实资质彩色标签、主号码/更多联系、详情及安全官网按钮、真实页码和10/20/50/100页长。

实际改动：frontend/src/business/product/Baichuan.tsx、CompanyDetail.tsx、Baichuan.css；frontend/tests/baichuan.test.mjs；services/business/backend/portal/baichuan_service.py（列表投影增加既有website字段）、portal/tests/test_baichuan.py；本SDD文档与refinement证据。未增加依赖或数据库迁移，未覆盖其他任务修改。

经公开原网页复核，使用既有经理账号、完整快照和expected_version接口为5家已有公司补充18个字段，保存前在线备份；总数1283不变。凯笙资料依据[公司官网](https://www.ksznkj.com/)，其他来源及新增字段见更新回执。没有改资质或人员；1462原始声明、289既有证据全部保留至正确公司。部分官网当前不可达，不宣称全部官网在线或所有资料均完成事实核实。

| 本轮实际检查 | 结果 | 证据 |
| --- | --- | --- |
| 百川阁前端定向 | 13/13 PASS | [定向日志](evidence/refinement-frontend-tests.txt) |
| 后端及权限/迁移检查 | 27/27 PASS；check及迁移漂移通过 | [后端日志](evidence/refinement-backend-tests.txt) |
| 类型、局部Lint、构建 | PASS；既有大包提示保留 | [构建日志](evidence/refinement-build.txt) |
| 隔离浏览器 | 14组PASS，含失败保留和版本冲突 | [浏览器日志](evidence/refinement-browser-regression.txt) |
| 真实双账号API及页面 | PASS；1283全集、筛选组合、页长、返回、官网新标签、复制成功与拒绝、参考布局 | [真实结果](evidence/refinement-live-results.json) |
| 最终字体 | 两账号×1440/1920共4组PASS；已实际查看最终截图 | [字体结果](evidence/refinement-font-results.json) |
| 数据修改与保留 | 5家18字段；资质/人员/账号角色模块不变，原始声明和既有证据完整 | [更新回执](evidence/refinement-update-result.json)、[保留对账](evidence/refinement-data-preservation.json) |
| 全套前端最新回归 | **84/85，1 FAIL** | [完整日志](evidence/refinement-frontend-regression.txt) |

全套失败位于frontend/tests/product-saved-draft.test.mjs:169：persisted review failures identify the paused stage and explain the error on the main card。其断言将SVG的line标签当成li边界；实际输出仍有总编复核标题。这是任务外既有修改，未覆盖或顺带修正，不能把全套标为通过。T-17的无关业务全站人工回归仍未执行。

真实截图及网页原件保持在Git外：C:/Users/BJRunner/.agent-reach/baichuan-20261016/refinement-page-evidence/，包括两账号各自reference-detail-1440.png、reference-detail-1920.png、list-1440.png、list-1920.png等；精确文件名前缀为manager_user或product_user。备份和更新预检在同级ui-refinement-update目录。

本机3080、8080服务保留；8100仅按原命令重启加载列表投影，健康及真实登录检查通过；本轮自用55173开发服务已停止。真实资料已初始化；仍需补充缺号/人员以及证书时效、主体和任职事实核实，未拨测电话，未实现自动联网刷新。下方V1.2的资料数量和检查为当时历史值，不覆盖本节最新结果。

## V1.2初始化交付记录（历史）

2026-10-16，SDD V1.2，当前工作区未提交。**当前本机平台已初始化全部1283家源表企业，现有总经理、产品账号真实HTTP及Chromium页面验证通过。** 企业收录全覆盖不代表电话、人员或证书真实性100%核实。

页面：[百川阁](http://127.0.0.1:3080/departments/product/baichuan)。两工作台保留各自外壳、共用同一库，均可新增编辑。用户先后确认查看和维护范围；当前部署显式配置general_manager/product读写角色，保留现有模块和服务端权限。没有新增/重置账号密码、改用户/角色/模块表或重置业务库。

## 最终实际交付

- 七类资质在服务端全量筛选、精确等级、同类OR/跨类AND、不限/具备即可，先去重计数再分页。源表82条CS一级按全覆盖要求补入原CS类别，未新增类别或高等级替代。
- 1283家全部可查询；1462条原始声明及289条公开补充证据完整可查；112条人员记录关联84家。人员来源时点、摘要/已读状态、电话用途和未提供项如实展示，不编造人才评级、当前职务、汇报关系或号码归属。
- 列表、详情、官网/来源安全HTTP(S)新标签；原子新增编辑、版本冲突和失败输入保留；仅PC、固定顶部侧栏、右侧正文滚动。长来源原生折叠，可展开全文，普通业务字段直接显示。无常驻导入页面。
- 一次性转换及初始化复用原有安全链：预检零写入、指纹、明确映射、原子事务、稳定ID、重跑跳过和后续维护冲突保护。正式导入前已在线备份现有SQLite及本机env，仅补执行0044增量迁移，审计操作人为已有manager_user。

## 数据覆盖与保留状态

| 项目 | 实际结果 |
| --- | --- |
| 公司/原始声明 | 1283个规范名称、1462条声明，原表总分表一致，不重复累加；不冒称工商主体已核验 |
| 筛选资质 | 1460条；另2条CCRC范围不明，只保留原文不冒认安全集成；5条含糊等级待补充；317条劳务不分级，A/AAA不作等级 |
| 公开证据 | 289条：133条已读页、156条搜索摘要；全部保留到正确公司来源 |
| 公开人员 | 112条涉及84家，含2个公开称谓；1199家尚未采到人员资料，不补造全名或核心团队 |
| 电话 | 原表1025家有可识别完整号；原缺号企业补得9家候选，共1034家包含候选电话证据，仍249家缺号。未拨测，项目/合同/招聘电话不冒认总机/个人号 |
| 官网 | 29个明确官方首页；其他网站线索保留来源，不冒认首页 |

源表中1139家一类、128家两类、15家三类、1家五类，没有六/七类真实样本；全七类组合使用独立夹具验证，没有在真实库编造样本。完整研究与来源限制见[data-source-review.md](data-source-review.md)。

## 最终检查与页面证据

| 检查 | 实际结果 | 证据 |
| --- | --- | --- |
| 后端/初始化/权限/并发 | 独立文件SQLite，27/27 PASS，零skip；迁移漂移及Django check通过 | [coverage-backend-tests.txt](evidence/coverage-backend-tests.txt) |
| 纯转换 | backend目录`python -m unittest portal.tests.test_baichuan_source -v`，7/7 PASS | [coverage-source-tests.txt](evidence/coverage-source-tests.txt) |
| 前端最终定向/全套 | `node --test`，定向16/16、全套82/82 PASS；全套有并行HMR端口提示，未失败，未改其他服务 | [定向](evidence/coverage-frontend-tests.txt)、[全套](evidence/coverage-frontend-regression.txt) |
| 类型/构建/局部Lint | tsc -b、vite build、指定组件ESLint均退出0；保留既有大包体积提示 | [coverage-build.txt](evidence/coverage-build.txt) |
| 原企业认证代理 | 初轮12/12 PASS | [bridge-tests.txt](evidence/bridge-tests.txt) |
| 隔离浏览器回归 | 14组PASS，含多等级、组合、详情返回恢复、官网、编辑失败输入保留、版本冲突、两壳固定布局 | [coverage-browser-regression.txt](evidence/coverage-browser-regression.txt)、[browser/results.json](evidence/browser/results.json) |
| 全源表独立库 | 1283名称、1462原文、289证据、112人员逐项对账；1283完整详情API和全分页；重跑0新增/1283跳过；双角色浏览器通过 | [coverage-isolated-results.json](evidence/coverage-isolated-results.json) |
| 正式本机初始化 | 预检1283公司/112人员、零错误；备份、0044迁移、整批事务及重跑通过；用户/角色/模块指纹及其他业务表计数不变 | [coverage-deployment-result.json](evidence/coverage-deployment-result.json) |
| 正式真实账号HTTP及浏览器 | 已有manager_user/product_user正常HTTP登录；各14页API全部1283名称相同，新增/编辑权限true；hr_user列表403；没有API替代或测试公司写入 | [coverage-live-results.json](evidence/coverage-live-results.json) |

正式Chromium在1440×900、1920×1080检查两工作台首屏1283家、65页末页3家、CS1=78家、CS1或2=95家、再且CMMI3=16家、名称搜索、详情返回、来源折叠展开、安全链接、真实官网新标签、公开人员和电话、刷新。pageerror为空。与参考图比较标题、副标题、蓝白卡片、七类横排筛选、四列表格；固定顶部侧栏、正文滚动及无横向溢出均通过。原有工作台菜单保留。

含真实资料的截图不提交Git，存于`C:/Users/BJRunner/.agent-reach/baichuan-20261016/live-page-evidence/`：两账号各有`*-list-1440.png`、`*-list-1920.png`、`*-combination.png`、`*-detail.png`、`*-detail-source-open.png`、`*-public-people.png`。主代理已实际查看列表及详情/人员截图。私人验证脚本为上级目录verify-platform.py、verify-live.py，日志platform-run-v3.txt、verify-live-final-run.txt。

## 改动与本机落地文件

原始实现文件详见下方初轮记录；本次追加/调整：

- `services/business/backend/portal/baichuan_models.py`、`baichuan_service.py`、`config/settings.py`：CS1及默认关闭的独立读写角色配置；settings其他任务修改保留。
- 新增`portal/migrations/0044_baichuan_cs_level_one.py`，依赖其他任务已有0043，不改写0042或0043。
- 新增`portal/baichuan_source.py`、`management/commands/prepare_baichuan_source.py`、`tests/test_baichuan_source.py`；调整`tests/test_baichuan.py`。纯转换无数据库写入，正式初始化仍走现有import_baichuan。
- `frontend/src/business/product/Baichuan-data.ts`、`CompanyDetail.tsx`、`Baichuan.css`、`frontend/tests/baichuan.test.mjs`、`baichuan-browser.py`：CS1、公开人员表述、来源安全链接及长文折叠、相关验证。
- `Baichuan.tsx`、`CompanyEditor.tsx`最终局部Lint发现并修正筛选状态在effect中同步、条件表达式及常量循环检查；筛选同步改用React同组件渲染时调整状态，保留连续多选。随后重新执行前端82项、类型检查、局部Lint、构建及两组浏览器验收；以最终日志为准。
- SDD的README/spec/plan/tasks/acceptance、资料核对、本报告及coverage证据已同步；未覆盖其他任务代码，未创建提交。

正式数据库：`C:/Users/BJRunner/Desktop/MultiUserClaw/services/business/.runtime/portal.sqlite3`。本机env新增范围确认及general_manager/product的独立读写角色配置；用户/角色/模块行未变。仅重启portal8100加载设置，8080和3080继续使用原进程。

正式SQLite备份、原env、预检、确认清单、事务回执位于私人目录`C:/Users/BJRunner/.agent-reach/baichuan-20261016/local-deployment-20261016-113713/`。源表/联系人/人员、工作簿及凭据均不提交Git。源文件SHA256=`220ec53ebe6a87263978f297891107700070d07588a4532b62ba884d64f68f07`；标准输入=`ff2599061e780a72a93542347255601f989ce59591a9a7788fbfc4ad589b897b`；映射=`23da7715a85570096c834f31189b066dd9ac818caf5e3abc47dce17cba32c9d0`；清单=`20ab7b245ffbab719cb176f8c7910aab185c6b671475b60c49827928c83469fa`。

## 未完成与依赖

1. 249家缺候选完整电话、1199家未采到人员，已有号码未拨测；摘要候选未全部读原页，人员现任、工商主体、证书有效性及含糊等级仍需可靠新来源/人工核实。全部公司已收录，缺项在页面保留，不能标100%资料核实。
2. 无关业务全站完整人工回归未执行，T-17因此部分完成；本功能与适用定向回归已完成，不能声称每条无关业务均验收。
3. 其他部署未迁移/初始化。本次实时展示为查询、刷新当前已保存资料，没有增加自动联网采集或资料事实自动更新。

真实资料已初始化，不再以Excel缺失或“仅功能验证”作为当前状态。

---

## 初轮隔离实施记录（历史阶段，非当前未完成状态）

以下保留首次实现时的改动和检查证据；当时D-02/D-03及源表待确认的状态已被上方真实初始化和页面验收结果取代。

## 实际完成内容

- 总经理、产品事业部的现有侧边栏接入百川阁，保留各自工作台外壳，通过同一 API 与数据库模型读取资料。
- 七类资质采用服务端全量筛选；同类多等级 OR、跨类 AND、等级精确匹配；不限、具备即可、未提供、不具备、等级待补充分开处理。去重、计数后分页；个人认证不计企业资质。
- 列表展示公司、地区、资质、联系方式；详情展示完整已录入公司资料、全部资质、来源及可选人员。官网只接受合法 HTTP(S)，安全新标签打开。
- 页面新增/编辑完整快照；统一服务端权限、字段错误、原子事务、子项归属、信用代码重复保护、版本 CAS、输入保留与未保存确认；保存后不再符合条件的公司移出结果并说明原因。
- PC 两种外壳固定侧栏与顶部，仅业务正文滚动；列表按参考图实现，右上为新增公司；没有常驻 Excel 导入页面或公司删除接口。
- 一次性 XLSX 初始化命令使用标准库 ZIP/XML，支持预检零写入、列名映射、原行与指纹、人工备注及多等级确认、原子导入、稳定 ID、重跑跳过、已编辑对象冲突与回执失败恢复。
- SDD 规格、方案、任务与验收记录同步到实施状态，未执行项保留待办。

## 改动文件

| 范围 | 文件（仓库相对路径） |
| --- | --- |
| 后端模型及查询/维护 | `services/business/backend/portal/baichuan_models.py`、`baichuan_service.py`、`baichuan_api.py`、`baichuan_urls.py` |
| 最小注册与迁移 | `services/business/backend/portal/models.py`、`services/business/backend/config/urls.py`、`services/business/backend/portal/migrations/0042_baichuan.py` |
| 一次性初始化 | `services/business/backend/portal/baichuan_import.py`、`services/business/backend/portal/management/commands/import_baichuan.py` |
| 后端检查 | `services/business/backend/portal/tests/test_baichuan.py`、`test_baichuan_import.py` |
| 页面 | `frontend/src/business/product/Baichuan.tsx`、`Baichuan-data.ts`、`Baichuan.css`、`CompanyDetail.tsx`、`CompanyEditor.tsx` |
| 导航与既有请求错误 | `frontend/src/enterprise-navigation.ts`、`frontend/src/components/Sidebar.tsx`、`frontend/src/business/product/ProductWorkspace.tsx`、`frontend/src/business/api.ts` |
| 前端检查 | `frontend/tests/baichuan.test.mjs`、`baichuan-browser.py`；更新 `manager-workspace.test.mjs`、`department-assistant.test.mjs` 的双入口预期 |
| 规格和证据 | `doc/baichuan-sdd/README.md`、`spec.md`、`plan.md`、`tasks.md`、`acceptance.md`、本报告及 `evidence/` |

`api.ts` 只为已有 ApiError 增加经过类型检查的字段错误，保留现有认证、凭据与代理调用。未引入新框架、运行时依赖或常驻导入服务。参考图和模板保持原用途。

实施前已有修改单独记录于 [初始状态](evidence/initial-status.txt) 和 [原文件指纹](evidence/protected-files.json)。最终 [复核](evidence/protected-verification.json) 中，21 个受保护已修改文件有19个字节级相同；`product_assistant_model.py` 与其测试在09:58/09:59出现任务外变化。本任务未写入这两文件，保留当前内容，没有回滚、覆盖或将其纳入百川阁实现。初始未跟踪的 `test_sqlite_transactions.py` 亦未改动。

## 实际检查

环境：Windows PowerShell 5.1/现有工具 PowerShell、Python 3.13.9、Django 5.2.17、项目自带 Node/npm、Playwright Chromium。未加载真实部署 .env；后端及浏览器均指定 `.runtime/` 中唯一隔离 SQLite。精确时间见各日志，浏览器结果附UTC时间。

| 检查 | 实际命令/步骤 | 结果与证据 |
| --- | --- | --- |
| 后端及初始化 | 仓库根 `powershell -NoProfile -ExecutionPolicy Bypass -File doc/baichuan-sdd/evidence/backend-command.ps1` | **24/24 PASS**，无跳过，含真实两个线程同版本竞争；[日志](evidence/backend-tests.txt) |
| 迁移与系统 | 同一隔离脚本执行 `manage.py makemigrations portal --check --dry-run`、`manage.py check` | 无迁移漂移、无系统问题，退出0；[日志](evidence/backend-checks.txt) |
| 前端定向 | `node --test frontend/tests/baichuan.test.mjs frontend/tests/manager-workspace.test.mjs frontend/tests/product-layout.test.mjs frontend/tests/department-assistant.test.mjs` | **16/16 PASS**；[日志](evidence/frontend-tests.txt) |
| 前端全部检查 | 项目 Node 执行 `--test`，参数为 `frontend/tests/*.test.mjs` 的所有文件 | **78/78 PASS**，无跳过；[日志](evidence/frontend-regression.txt) |
| 前端构建 | frontend目录 `npm run build` | 退出0；[日志](evidence/frontend-build.txt)。现有打包体积警告仍在，不扩大本次范围处理 |
| 现有认证/企业代理 | `.runtime/python/Scripts/python.exe -m unittest discover -s platform/tests -p test_business_bridge.py` | **12/12 PASS**；[日志](evidence/bridge-tests.txt) |
| 真实浏览器 | 独立Vite55173 + `.runtime/python/Scripts/python.exe frontend/tests/baichuan-browser.py` | **14组检查 PASS**，退出0；[运行输出](evidence/browser-run.txt)、[结构化结果](evidence/browser/results.json) |

浏览器使用真实 React 页面、真实 JWT 登录、现有 FastAPI 企业代理、Django 视图及 CSRF、隔离数据库；代理到Django用进程内测试传输，没有写入真实业务数据。OpenClaw无关指标、官网外页使用隔离占位；保存/查询503和断网按用例主动注入。P1最近项目未在隔离配置启用，其503按原壳真实显示，不冒称无关业务已正常运行。未预期请求与浏览器 pageerror 均为0。

前端全套日志中存在测试环境 HMR 端口24678占用提示，测试退出0；未改动或终止其他服务。构建通过不能替代真实部署验收。

本轮浏览器检查曾发现首击复选框受URL过渡延迟影响、末页越界误用无匹配文案，以及服务端字段错误焦点早于禁用状态解除的偶发时序问题，均修正后重新执行相应验证。初始化复核修正了人工多等级映射可能漏掉同一行其他非空资质的问题，并加入检查后重跑24项通过。浏览器竞态测试也改为等待旧请求实际到达后再释放，避免把“已显示加载中”当作“服务请求已被挂起”。证据目录保留最终执行结果；不将中间失败记为通过。

## 页面验证证据

| 业务行为 | 实际结果 | 页面证据 |
| --- | --- | --- |
| 精确/多等级/跨类 | 二级仅B/E；一级+二级A/B/C/E/F；再CMMI三级A/E；再ITSS二级A | [多等级](evidence/browser/multi-grade.png) |
| 列表与外壳 | 两类工作台分别保留原导航；1440和1920均无横向溢出，滚动正文不改变侧栏/顶部位置；逐类展开全部七类菜单验证选项数量、弹层边界与外部点击关闭 | [经理1440](evidence/browser/manager-list-1440.png)、[经理1920](evidence/browser/manager-list-1920.png)、[产品1440](evidence/browser/product-list-1440.png)、[产品1920](evidence/browser/product-list-1920.png) |
| 详情返回与官网 | E显示全部3条资质、只标1条命中；两种返回恢复第2页与255px滚动；刷新保留查询；官网新标签 | [详情](evidence/browser/detail.png) |
| 保存失败与冲突 | 本地必填/信用代码、真实400、注入503保留输入；另一会话保存后本会话409，旧草稿保留，关闭/返回取消继续编辑 | [失败草稿](evidence/browser/save-failure-preserved.png)、[失败提示](evidence/browser/save-failure-alert.png)、[冲突草稿](evidence/browser/version-conflict.png)、[冲突提示](evidence/browser/version-conflict-alert.png)；错误断言及状态见results.json |
| 条件变化及竞态 | 删除A命中资质后结果C/E/F且有说明；旧B查询最后返回仍显示新F | [查询竞态](evidence/browser/query-race.png)及results.json |
| 新增与可选人员 | 仅名称真实创建，再添加同类两个等级及一名录入人员；电话前导零保留，清空人员日期保存null | [详情与人员](evidence/browser/created-company-team.png) |
| 异常及空态 | 越界页、实际404、加载、无匹配、无权、503、断网恢复、隔离空库均区分 | [空库](evidence/browser/empty-library.png)及results.json |

截图中的公司与人员均为验收夹具；产品截图在“删除A命中资质”检查之后生成，因此A的摘要与初始经理截图不同，这是实际编辑结果。截图只记录可见区域；完整断言与状态记录以结构化结果和可复跑脚本为准。

## 权限与真实初始化待办

1. **D-02/D-03：PENDING_POLICY。** 确认真实读取者、创建/编辑者、当前部署代表的共享范围。默认 `PORTAL_BAICHUAN_SCOPE_CONFIRMED=False`、读写用户ID名单为空，且仍需已有产品模块和角色权限。本轮只在隔离设置中显式给测试M/P/R授权，没有开放真实账号。最终策略不同应先同步规格和验收。
2. **D-04：PROVIDED_PENDING_REVIEW。** 企业名录已提供并完成首轮只读结构预检、总分表核对及逐家检索；仍须核对主体、等级映射、人员归属与资料时效，生成确认后的目标模板和正式初始化清单。不得把研究补充表或测试工作簿作为真实初始化完成。
3. **目标环境与执行：NOT_RUN。** 目标部署/数据库未明确，未在真实库执行0042迁移、初始化命令或任何重置。先保存目标环境备份和预检清单，人工核对确认后，再在获准目标运行一次性命令；权限名单、清单和真实资料不得提交仓库。
4. **真实身份及全站人工回归：NOT_RUN。** 本轮通过已有78项前端和12项代理回归，尚未使用真实账号完成正式验收，也未跑全站文档/报价/助手/商机业务端到端回归。T-13真实身份部分、T-15/T-16及T-17全量关闭保持未完成。

命令实现可用，下面是后续真实执行的形状，并非本轮已经执行：

```text
python manage.py import_baichuan --input final.xlsx --dry-run --report preview.json
# 人工处理所有疑点，复核文件/映射/目标，并在对应manifest中明确 confirmed=true。
python manage.py import_baichuan --input final.xlsx --apply --manifest confirmed.json --actor 已授权现有用户名 --report receipt.json
```

使用自定义列名或多等级归一时，两步都传相同 `--mapping mapping.json`。映射中的 `notes_reviewed` 必须匹配原备注，`qualification_overrides` 必须完整覆盖原行所有非空类别；源表、映射或目标快照变化后必须重新预检。已编辑记录报告冲突，不用旧表覆盖。

目前可声明的是：**功能已在隔离环境验证；真实资料初始化待完成。**


## 2026-10-16 全工作区代码同步检查

用户指定目标为 qiyuxrang/NewAi_platform，范围包含产品事业部、工程部、总经理及其他现有模块的全部当前代码改动。既有工程部和总经理基础代码已包含于共同基线，本次同时纳入所有未提交的工作区源码、迁移、测试、参考素材与开发文档，不只提交百川阁。凭据、真实业务数据库、研究原始文件、依赖与本机运行缓存不作为代码上传。

本次完整前端测试92/92通过，TypeScript与Vite生产构建通过；构建仍有大体积chunk提示，测试输出含既有24678热更新端口占用提示，不影响退出成功。对应记录为 evidence/github-sync-frontend-tests.txt、github-sync-build.txt；早期报告的84/85是历史结果，本次不再沿用为当前测试状态。百川阁后端28/28、系统检查/迁移一致性和隔离浏览器15组结果见homepage-types系列证据；其他模块后端全套及全站人工业务回归本次未执行。

官方主页类型功能及0045增量迁移已验证，真实替代主页资料补录/页面复验、第二轮事实最终审查入库仍未完成，不因上传代码而标为资料全覆盖。T-17、T-28与T-29保留各自未完成边界。

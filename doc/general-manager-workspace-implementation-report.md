# 总经理工作台与部门填报实施交付

日期：2026-10-14。当前已完成五入口、统一布局、三类填报、财务只读看板及精简 BI，并在用户要求整体上线及逐项账号授权确认后，完成本机实际库最小迁移、实际账号接入、构建产物部署与真实只读浏览器验收。61 项前端测试、旧身份/桥接与财务检查、两套前端构建、隔离交互验收通过；实际环境 15 组检查、22 张成功截图。随后按用户要求少量代表性验证，3 个业务场景和 1 次冲突检查在实际库副本＋原后端 HTTP 中通过，长金额排版已修正并部署。真实台账保存/发布、知识问答模型调用及生成/报价任务未执行，源表单位和年度仍未核实。第 1—8 节保留阶段历史，实际部署见第 9 节，最新代表性验证及限制见第 10 节。

## 1. 本轮结果

| 范围 | 实施结果 |
| --- | --- |
| 总经理五入口 | 商机看板、文档生成、产品报价、知识检索、财务看板，按 SDD 顺序；根据既有 capability 显示可用项。财务采用独立总经理守卫。 |
| 统一布局 | 企业 Logo 保留；固定 224px 侧栏、60px 顶栏，右侧滚动；最近项目、账号、设置沿用现有接口和操作。五页共用外壳，每条业务路径只有一层 BusinessSurface。减少动画设置有效。 |
| 文档导航 | 默认历史项目；历史项目、新建项目、成果文件内部入口，以及 task 详情、深链接、刷新、前进/后退均沿用现有页面。普通产品员工原工作台保留。 |
| 售前填报 | 六项主字段，其他信息展开；记录按自身标准/源表模式处理。完整原字段随单条记录保存，原始金额及单位只读保留；空白阶段、日期、源表折算金额不补零。 |
| 工程填报 | 五项既有字段；与报价页分离。未知进度保持空白并阻止有效保存，真实 0% 可填写；未加入新字段或计算。 |
| 台账操作 | 先读取既有权限；按状态及服务端 permissions 分别允许编辑、提交、发布、退回。每次写入携带 expected_revision。409 保留输入，读取最新版本后人工核对；未经核对不自动重试。未保存离开和浏览器后退取消保留输入。 |
| 财务只读看板 | 已发布数据、同一服务端筛选范围下的指标/分布/明细；标准模式四项指标、已收/待收环形图、结清数量图。源表模式五项指标、仅数量分布，明确原表金额单位未核实。401/403 显示真实错误并清除旧内容。 |
| 商机 BI | 公告既有四项统计，线性图标与一张新增/截止独立条形图；注明指标可能重叠。未用分页数据推算总数，未混入售前阶段或金额。 |

财务看板没有写入、导入、发布或权限变更操作。未知金额显示“—”；源表年度不根据截止日期推定。

## 2. 冻结及现有改动保护

实施前记录了当前工作区 `platform` 与 `services` 中 580 个 Git 跟踪或非忽略未跟踪文件的 SHA-256，而非仅对照 HEAD。结束核对：**580/580 一致，新增受保护文件 0，企业 Logo 哈希一致**。平台鉴权/身份桥接、文档和报价契约、任务、Worker、模型、计算、存储及下载后端均未修改。

- [实施前状态](implementation-evidence/initial-status.txt)
- [后端基线](implementation-evidence/backend-baseline.json) / [结束核对](implementation-evidence/backend-verification.json)
- [Logo 基线](implementation-evidence/logo-baseline.json)
- [本轮源文件差异及哈希](implementation-evidence/frontend-change-manifest.json)
- [原有修改仍完全一致的前端文件](implementation-evidence/existing-edits-unchanged.json)

`business/api.ts` 相对实施前仅在合法地址根中增加 `business`；已有认证头、代理转换、上传、错误、预览和下载实现保持原样。`DocumentWorkspace.tsx`、`ProjectStages.tsx`、`product-api.ts`、报告状态/公共组件与实施前哈希一致，未借本轮修改报告生成逻辑。

没有导入真实工作簿、提交真实填报、触发真实生成或报价任务、修改真实账号授权，也没有执行数据库迁移。浏览器全部 API 请求由隔离 fixture 拦截；保存、提交和发布只修改测试内存数据。

## 3. 本轮改动清单

以下清单是相对本轮开始状态的增量；`git diff HEAD` 还包含用户原有改动，不能将其全部归于本轮。

| 文件 | 本轮变更 |
| --- | --- |
| `frontend/src/enterprise-navigation.ts` | 总经理入口、独立财务守卫、员工入口资格。 |
| `frontend/src/App.tsx` | 财务与填报路由守卫，原路由继续复用。 |
| `frontend/src/main.tsx` | 在 BrowserRouter 初始化前安装填报导航边界，避免浏览器后退先卸载表单。 |
| `frontend/src/components/Layout.tsx` | 总经理统一外壳和内容淡入；员工布局保留。 |
| `frontend/src/components/Sidebar.tsx` | 五入口、高亮、最近项目、按权限显示填报入口。 |
| `frontend/src/components/TopBar.tsx` | 总经理路径和账号显示，原操作保留。 |
| `frontend/src/components/RecentProjects.tsx`（新增） | 既有项目列表的只读最近项目。 |
| `frontend/src/components/manager-workspace.css`（新增） | 固定外壳、单层产品布局、文档内部导航。 |
| `frontend/src/pages/EnterpriseHome.tsx` | 授权总经理五卡片和员工入口筛选。 |
| `frontend/src/pages/DepartmentWorkspace.tsx` | 复用原部门页面，区分填报、报价和财务。 |
| `frontend/src/business/product/ProductWorkspace.tsx` | 总经理单列外壳、历史默认页和三项文档导航；员工入口补充。 |
| `frontend/src/business/product/TenderOpportunities.tsx` | 仅总经理显示精简商机 BI。 |
| `frontend/src/business/product/tender-opportunities.css` | 商机图标、小图样式。 |
| `frontend/src/business/api.ts` | 增补 business 地址根。 |
| `frontend/src/business/workspace-navigation.ts` | 新建项目显式 `view=new`，兼容历史路由跳转。 |
| `frontend/src/business/entry-access.ts`（新增） | 按身份及既有台账权限决定入口可见性。 |
| `frontend/src/business/finance/FinanceBoard.tsx`、`finance-board.ts`、`finance-board.css`（新增） | 财务 GET 展示、格式化、真实错误及小图。 |
| `frontend/src/business/ledgers/LedgerEntry.tsx`、`ledger-api.ts`、`ledger-state.ts`、`ledger-navigation.ts`、`ledger-entry.css`（新增） | 两类表单、原字段保护、单条版本写入、状态操作、导航保护及样式。 |
| `frontend/scripts/check-business-navigation.mjs` | 新建项目导航期望更新。 |
| `frontend/scripts/check-sdd-freeze.mjs`（新增） | 可重复执行的后端/Logo 冻结核对。 |
| `frontend/scripts/accept-workspace-sdd.mjs`（新增） | 桌面 Chromium 隔离验收与截图；默认访问现有本地 Vite 3080，可用 `SDD_BROWSER_URL` 指定地址。 |
| `frontend/tests/manager-workspace.test.mjs`、`finance-board.test.mjs`、`ledger-entries.test.mjs`、`opportunity-bi.test.mjs`（新增） | 定向权限、请求语义、字段/版本/导航和未知值检查。 |
| `frontend/tests/product-layout.test.mjs` | 原有员工布局测试增补身份上下文 mock。 |
| 本报告及 `doc/implementation-evidence/` | 基线、检查结果、回归失败证据与截图。 |

没有新增 npm 依赖。商机/财务图表使用既有图标与 SVG/CSS。独立填报、财务、商机任务按 AGENTS.md 由子代理负责，共享导航和外壳由主代理统一修改并最终验收。

## 4. 实际验证（首轮记录）

本节保留首次交付结果；继续收尾后的最新结果以第 7 节为准。原始失败日志没有覆盖或删除。

| 检查 | 结果及证据 |
| --- | --- |
| `node frontend/scripts/check-enterprise-navigation.mjs` | PASS。原检查文件未修改。 |
| `node frontend/scripts/check-business-navigation.mjs` | PASS。 |
| 五组定向测试 | 15/15 PASS：[完整输出](implementation-evidence/targeted-checks.log)。 |
| 改动的 TS/TSX 定向 ESLint | 退出码 0，无错误。 |
| `npm --prefix frontend run build` | PASS：TypeScript 与 Vite 完成，1849 模块；保留产物大于 500KB 的构建警告，本轮没有为此改造分包。 |
| `node frontend/scripts/check-sdd-freeze.mjs` | PASS：580 文件及 Logo 一致。 |
| `node frontend/scripts/accept-workspace-sdd.mjs` | PASS：五页 × 两尺寸 = 10 次总经理布局检查；两类填报各两尺寸；5 组交互验证。[结果、几何数据与请求明细](implementation-evidence/browser-results.json)。 |
| 扩大既有前端回归 | 31 项，27 PASS、4 FAIL；[当前日志](implementation-evidence/expanded-regression.log)。 |
| `node frontend/scripts/check-product-reports.mjs` | FAIL：第 47 行预期 `blocked`，实际 `completed`。实施前隔离版本同样失败：[基线日志](implementation-evidence/baseline-product-reports.log)。 |

定向测试命令：

```powershell
node --test frontend/tests/manager-workspace.test.mjs frontend/tests/product-layout.test.mjs frontend/tests/opportunity-bi.test.mjs frontend/tests/finance-board.test.mjs frontend/tests/ledger-entries.test.mjs
```

桌面验收使用真实 Chromium，1440×900 与 1920×1080。验证侧栏及顶栏几何位置、无整页横向溢出、单层业务外壳、默认历史项目、新建/成果流转、前进/后退、深链接刷新、详情、既有预览图片及下载字节、服务端筛选范围、源表无金额图、401/403、部分授权、未授权填报和财务拒绝、减少动画、两类台账 409 输入保留与人工合并、模拟提交/发布、未保存点击及后退取消。

浏览器阶段发现并修正了知识页沿用员工网格列导致的空列，以及原 popstate 监听晚于 Router 导致取消后退失效的问题。完整浏览器验收在修正后重跑通过。浏览器只证明前端在隔离返回数据下的行为，不代表实际账号、真实业务后端或生产生成任务的联调通过。

## 5. 截图

全部截图使用隔离验收样例，数字、人员和项目不是企业真实台账。

| 页面 | 1440×900 | 1920×1080 |
| --- | --- | --- |
| 商机看板 | [截图](implementation-evidence/opportunities-1440.png) | [截图](implementation-evidence/opportunities-1920.png) |
| 文档历史项目 | [截图](implementation-evidence/documents-1440.png) | [截图](implementation-evidence/documents-1920.png) |
| 产品报价 | [截图](implementation-evidence/estimate-1440.png) | [截图](implementation-evidence/estimate-1920.png) |
| 知识检索 | [截图](implementation-evidence/knowledge-1440.png) | [截图](implementation-evidence/knowledge-1920.png) |
| 财务看板 | [截图](implementation-evidence/finance-1440.png) | [截图](implementation-evidence/finance-1920.png) |
| 售前填报 | [截图](implementation-evidence/presales-entry-1440.png) | [截图](implementation-evidence/presales-entry-1920.png) |
| 工程填报 | [截图](implementation-evidence/engineering-entry-1440.png) | [截图](implementation-evidence/engineering-entry-1920.png) |

补充：[文档详情与预览](implementation-evidence/document-detail-1920.png)、[财务源表模式](implementation-evidence/finance-source-1920.png)、[财务403](implementation-evidence/finance-403.png)、[售前编辑](implementation-evidence/presales-editor-1920.png)、[售前版本冲突](implementation-evidence/presales-conflict.png)、[工程编辑](implementation-evidence/engineering-editor-1920.png)、[工程版本冲突](implementation-evidence/engineering-conflict.png)。

## 6. 未完成、保留与回归限制

1. **财务员工身份及财务填报：第一阶段暂缓，现已获准并实现。** 第 8 节给出身份、界面及隔离验证；实际库尚未迁移、实际账号尚未上线，不能将隔离通过等同于真实接入完成。
2. **真实业务联调：未执行。** 未通过真实保存、提交、发布、生成、报价或导入验证生产链路，符合本轮约束。现有真实授权与 API 拒绝仍由原后端决定。
3. **源表金额单位及年度核实：未完成。** 界面明确显示未知；未绘制源表金额图。不会因后台返回“元”就认定原表单位正确。
4. **首轮五个报告验证失败已完成核查与适配。** 以下四个失败在实施前源文件的隔离副本也逐项复现，基线 19 项为 15 PASS/4 FAIL；另有报告检查脚本的状态断言失败。继续收尾证实四个 SSR 断言预期收起详情仍渲染全文，与原有按需显示冲突；第五个断言把已保存正文节点强制改成 blocked，与服务端独立保存的节点状态不一致。生产报告源码未改；保留核心业务断言，增加真实展开验证及状态边界检查后通过。第 7 节列出变更、当前结果和截图。

| 失败测试名称 | 涉及预期 |
| --- | --- |
| `saved body with the wrong report family is excluded even when title and sources match` | 报告族不匹配的正文排除。 |
| `current files remain downloadable during running or failed tasks with honest quality warnings` | 已有文件与质量提示。 |
| `quality warning survives before file generation and exhausted recovery remains disabled` | 生成前质量提示和恢复额度。 |
| `incomplete delivery offers recovery and real blocking reasons while keeping all saved downloads` | 不完整交付的恢复、阻断原因及下载。 |

历史证据：[四个失败对照](implementation-evidence/baseline-regression-failures.json)、[基线完整测试日志](implementation-evidence/baseline-tests.log)、[基线运行记录](implementation-evidence/baseline-test-result.json)、[关键源文件哈希对照](implementation-evidence/baseline-critical-source-hashes.csv)。隔离副本使用实施前源文件与当时相同的既有测试。这些记录保留为首轮结果，不能将本次测试适配描述为修复了真实后端生成问题。

## 7. 继续收尾：当前结果

用户明确将纯前端报告问题纳入收尾，后端继续冻结。独立调查与主代理真实浏览器复核一致：已保存正文只在展开章节后挂载，质量与交付问题只在展开详情后挂载；正确报告族正文可见，错误报告族正文被过滤。正文节点 completed、篇幅待补、草稿待完善是三个不同事实，界面均保留；真实 failed/blocked 不改写，缺失节点仍 pending。

### 继续收尾的增量

本次只修改 5 个验证文件和交付报告/证据；`frontend/src` 的 109/109 文件与继续前一致，文档与报价生产实现、全部受保护后端及 Logo 仍保持原值。

- `frontend/scripts/check-product-reports.mjs`：completed 正文节点同时验证实际字数、最低字数、篇幅待补提示；增加真实 failed/blocked 保留、缺节点不能由任务完成或字数推定完成的检查。
- `frontend/tests/product-dual-blueprint.test.mjs`：直接执行生产正文过滤函数，断言仅有效章节及各报告族正文正/负条件；初始 SSR 验证一章摘要和收起时正文不挂载。
- `frontend/tests/product-saved-draft.test.mjs`：保留文件下载、草稿、图表数量、篇幅、额度检查；初始 SSR 验证问题计数/展开入口，原始问题文字由浏览器展开验证。
- `frontend/tests/product-presentation-workspace.test.mjs`：保留恢复入口、草稿和四个下载按钮检查；初始 SSR 验证交付问题计数及展开入口，完整原因由浏览器展开验证。
- `frontend/scripts/accept-workspace-sdd.mjs`：结果按时间戳另存，保留旧证据；严格验证两类台账单条/日期/状态写入契约，工程并发样例使用既有 owner 字段；补权限矩阵、必填无写入、显式零值、前进取消/确认，以及五个报告展示场景。测试导航等待页面稳定，避免确认离开后马上读取新页面造成执行上下文销毁。

生产源码保持不变，因此本次没有借修复测试修改生成规则、篇幅计算、恢复操作、下载实现或批准流程。修改前四个既有验证文件也已备份，调查记录保留修改前哈希。

### 最终验证

| 检查 | 当前结果 |
| --- | --- |
| 全部现有前端测试 | **48/48 PASS**，串行运行全部 11 个 `.test.mjs`：[日志](implementation-evidence/continuation-all-tests.log)。 |
| 三项现有脚本 | 企业导航、业务导航、报告检查均 PASS；报告脚本含认证下载隔离检查：[日志](implementation-evidence/continuation-validation/report-validation-script.log)。 |
| 前端构建 | **PASS**，产物 hash 与继续前相同；仍有原有 500KB chunk 警告：[日志](implementation-evidence/continuation-build.log)。 |
| 继续阶段源码核对 | **109/109 一致**：[证据](implementation-evidence/continuation-source-verification.json)。 |
| 后端与 Logo 冻结核对 | **580/580 一致、无新增受保护文件、Logo 一致**：[证据](implementation-evidence/backend-verification.json)。 |
| 最终完整 Chromium 验收 | **PASS**：10 次总经理尺寸检查、6 组交互、5 个报告场景；售前和工程分别通过状态/权限/导航检查：[结果与所有请求明细](implementation-evidence/browser-run-2026-10-14T06-15-34-159Z/browser-results.json)。 |

全部前端测试命令：

```powershell
$taskTests = @(rg --files frontend/tests | Where-Object { $_ -like '*.test.mjs' })
node --test --test-concurrency=1 $taskTests
node frontend/scripts/accept-workspace-sdd.mjs
```

补充浏览器验证事实：两类填报各有三次取消提示（点击、后退、前进）与一次确认前进；确认离开前后 fixture 写入均为 8 次，没有离开隐式写入。空工程进度、标准售前缺金额或阶段均不发 POST，填写真实 0 后可新增。保存截止日期、提交、退回、重新提交、发布逐个携带准确 expected_revision。三种权限矩阵分别检查“能提交但不能编辑/发布”“已提交且仅编辑授权”“已提交且仅发布授权”。

五个报告场景为正文族隔离、RUNNING 质量提示、FAILED 质量提示、未生成文件但有质量问题且恢复额度为零、不完整交付原因；全部只读，报告写入 0。用户实际点击展开后，正文、原始问题文字、代码对应原因都可见；保存文件的下载按钮保留，额度为零的恢复按钮禁用。

新增截图：[技术正文展开](implementation-evidence/browser-run-2026-10-14T06-15-34-159Z/report-family-technical-solution.png)、[可研正文展开](implementation-evidence/browser-run-2026-10-14T06-15-34-159Z/report-family-feasibility.png)、[运行中质量提示](implementation-evidence/browser-run-2026-10-14T06-15-34-159Z/report-quality-running-expanded.png)、[失败状态质量提示](implementation-evidence/browser-run-2026-10-14T06-15-34-159Z/report-quality-failed-expanded.png)、[尚无文件的质量提示](implementation-evidence/browser-run-2026-10-14T06-15-34-159Z/report-no-file-expanded.png)、[交付原因展开](implementation-evidence/browser-run-2026-10-14T06-15-34-159Z/report-delivery-expanded.png)、[售前取消前进](implementation-evidence/browser-run-2026-10-14T06-15-34-159Z/presales-dirty-forward-cancelled.png)、[工程发布权限](implementation-evidence/browser-run-2026-10-14T06-15-34-159Z/engineering-publisher-permissions.png)。仍全部使用隔离样例。

[独立调查、断言适配和关键源码哈希记录](implementation-evidence/continuation-validation/report-validation-investigation.json)；[三组报告测试 19/19 输出](implementation-evidence/continuation-validation/report-validation-unit-tests.log)。过程中的浏览器等待失败也另存，未当作 PASS；最终结果以本节完整重跑为准。

本节为继续收尾阶段的历史状态；最新财务前置包与全量隔离验收见下节。实际库迁移、真实业务联调及源表单位核实仍不在已完成项中。

## 8. 全量实施及财务前置包（隔离验收阶段历史）

用户明确授权：“允许财务前置包，先隔离验证；实际库迁移另行确认”。本阶段完成 SDD 的代码与隔离验收；实际财务账号上线仍待迁移批准及后续正常绑定验收。未扩大原业务 grant、借用总经理身份或添加产品/工程权限。

### 增量改动清单

| 文件 | 实现内容 |
| --- | --- |
| `frontend/src/business/finance/FinanceEntry.tsx`、`finance-entry.ts`、`finance-entry.css` | 财务本人记录填报；标准四项与源表七项主字段、主体/月度展开区；标准/源表/混合列表；完整原记录合并；本人精确版本发布、已发布快照与版本基线；409 人工核对。 |
| `frontend/src/enterprise-navigation.ts`、`pages/DepartmentWorkspace.tsx`、`lib/api.ts` | 增加财务员工类型、部门及 `/departments/finance/entry`，复用原守卫、侧栏、权限读取和业务代理。GM 五入口和原三部门 capabilities 不变。 |
| `manage_front/src/types/index.ts`、`lib/business-assignment.ts`、`app/(admin)/users/page.tsx` | 管理员现有分配界面增加财务选项；沿用原授权管理员创建/更新接口，不创建或修改实际账号。 |
| `platform/app/enterprise.py`、`db/models.py`、`business_client.py` | finance 枚举和 CHECK；仅原门户核实为财务部门、非 GM、business 已启用且现有权限接口明确返回 finance grant 才识别财务员工。旧三部门及 GM 请求顺序、会话、CSRF、代理、下载函数保持。 |
| `platform/alembic/versions/20261014_finance_department.py` | 在线 PostgreSQL 增量迁移，仅更换 `users.ck_users_department_code`。旧表/列/约束缺失明确失败；存在财务账号时回退拒绝且原子保持，不删除或静默改派账号。 |
| 新财务前端、身份及迁移测试；现有导航、分配测试 | 新增本人/他人/未知作者、完整字段、零值/空值、模式转换禁用、已发布基线、精确发布、冲突、撤权检查。旧无效部门夹具仅从现已合法 finance 改为 unknown。 |
| `frontend/scripts/accept-workspace-sdd.mjs`、`check-finance-sdd-freeze.mjs` | 补充财务桌面交互与完整写入契约；独立记录批准的身份/约束差异，保留原冻结基线与历史证据。 |

财务记录编辑按原记录口径分组，不能通过清空最后一个来源判定字段或填写源表字段把已有标准/源表记录相互转换；新增不能主动混入不同口径。原有混合数据仍按单条校验、完整保留，统计继续采用原 API 口径。来源工作表/行只读，新增没有伪造来源。源表未知金额与月份空值不补零，标准已收金额仍必填。源年度不由截止日期或“手工录入”猜测。

财务操作只有保存本人草稿和确认本人精确版本发布，没有部门提交/退回按钮。发布条件使用既有 can_edit、已核实作者及最后修改人，不能由通用 can_publish 推定；请求准确包含 expected_revision、expected_published_revision 和每条 record_id/source_revision/source_checksum。已发布版本列表达到现有 200 条上限且没有发布基线时保持“未核实”，禁用发布。

### 实际验证

| 检查 | 结果及证据 |
| --- | --- |
| 全部前端测试 | **61/61 PASS**，12 个文件，[日志](implementation-evidence/finance-all-frontend-tests.log)。 |
| 三项现有检查 | 企业导航、业务导航、产品报告均 PASS；报告生成/恢复/下载源码未改。 |
| 财务身份及旧链路 | 财务身份 8、旧业务桥接 11、旧企业身份 14，共 **33/33 PASS**，全为 mock 门户和内存 SQLite；[财务](implementation-evidence/finance-identity-tests.log)、[桥接](implementation-evidence/finance-business-bridge-regression.log)、[身份](implementation-evidence/finance-enterprise-identity-regression.log)。 |
| PostgreSQL 迁移定向测试 | **3/3 PASS，无 SKIP**。全新 Docker PG16 临时数据库的随机 schema：旧完整行保持、接受 finance、拒绝非法部门、有 finance 拒绝回退、显式恢复后回退、缺表/列/约束失败。[日志](implementation-evidence/finance-postgresql-migration-tests.log)。 |
| Alembic CLI 端到端 | **PASS**，全新隔离库 public 旧表执行 upgrade head；旧数据完整相等，版本表正确；有 finance 的 downgrade base 原子拒绝，原约束和记录保持；显式恢复合成账号后降级成功；再次升级及重复升级成功。[可复跑脚本](implementation-evidence/finance-isolated-alembic-check.py)、[日志](implementation-evidence/finance-alembic-cli.log)。 |
| 原财务及台账服务回归 | **19/19 PASS**，原 Django 测试、独立内存测试库；含只发布本人选定记录、其他人禁止、精确 checksum/revision 冲突、草稿不入 GM 看板、发布后更新且保留他人已发布记录。[日志](implementation-evidence/finance-portal-regression.log)。 |
| 管理员分配检查 | **8/8 PASS**，含财务分配仍使用原认证管理员 PUT 契约；没有真实写请求。[日志](implementation-evidence/finance-admin-check.log)。 |
| 构建及定向 lint | 业务前端及 Next 管理前端 build PASS，改动 TS/TSX 定向 lint PASS。[业务构建](implementation-evidence/finance-frontend-build.log)、[管理构建](implementation-evidence/finance-admin-build.log)、[业务 lint](implementation-evidence/finance-frontend-lint.log)、[管理 lint](implementation-evidence/finance-admin-lint.log)。业务前端原有大 chunk 警告仍在；前端全测的临时 Vite 有现存 HMR 端口占用提示，测试仍 61 PASS，没有改运行服务。 |
| Chromium 完整验收 | **PASS**，保留五入口 10 次尺寸检查、原售前/工程与报告场景，新增财务标准/源表各两种桌面尺寸；本人/他人/未知归属、12 月空值与真实零、409 只写一次后人工核对、精确本人发布、原字段/他人快照保留、无 grant、未保存离开取消、403/401 清旧内容均通过。所有 API 拦截，真实业务透传 0。[结果与请求明细](implementation-evidence/browser-run-2026-10-14T06-47-10-467Z/browser-results.json)。 |
| 冻结范围核对 | 原 580 文件中 **576 未变**；4 个既有文件变化严格为获准平台身份/约束及一处测试夹具；新增受保护文件仅迁移和 2 个测试。**services 全部保持、未授权差异 0、Logo 一致**。[结果](implementation-evidence/finance-backend-verification.json)。 |

### 截图

全部为隔离数据；原五入口、售前、工程及报告截图也在同一目录。

- [财务标准列表 1440](implementation-evidence/browser-run-2026-10-14T06-47-10-467Z/finance-entry-standard-1440.png)、[1920](implementation-evidence/browser-run-2026-10-14T06-47-10-467Z/finance-entry-standard-1920.png)
- [财务源表列表 1440](implementation-evidence/browser-run-2026-10-14T06-47-10-467Z/finance-entry-source-1440.png)、[1920](implementation-evidence/browser-run-2026-10-14T06-47-10-467Z/finance-entry-source-1920.png)
- [源表月份展开](implementation-evidence/browser-run-2026-10-14T06-47-10-467Z/finance-entry-source-months.png)、[源表冲突核对](implementation-evidence/browser-run-2026-10-14T06-47-10-467Z/finance-entry-conflict-source.png)、[标准冲突核对](implementation-evidence/browser-run-2026-10-14T06-47-10-467Z/finance-entry-conflict-standard.png)、[撤权清空](implementation-evidence/browser-run-2026-10-14T06-47-10-467Z/finance-entry-403.png)

### 未完成项与实际库迁移门槛

1. **实际库迁移尚未执行，必须另行确认。** 实际库只读核查为原三部门 named CHECK，尚无 Alembic 版本表；[迁移前核查](implementation-evidence/finance-actual-db-before.txt)与[结束核查](implementation-evidence/finance-actual-db-after.txt)完全一致。候选迁移 revision 为 `20261014_finance_department`，唯一业务 DDL 是增加 finance 部门 CHECK，Alembic 自建版本表用于版本记录；不改业务数据。确认实际目标、备份与执行窗口后，使用目标服务的真实 `PLATFORM_DATABASE_URL` 从 platform 目录执行 `python -m alembic upgrade head`。不要仅改 alembic.ini：现有 env.py 以 settings 覆盖连接 URL。**本报告中的命令尚未对实际库执行。**
2. **真实财务账号绑定/上线验收未执行。** 代码、mock 链路和隔离 DB 已完成；需实际迁移及加载新平台代码后，用原财务身份与真实已有 grant 正常绑定验证。不改员工所属部门，不借用其他模块或 GM 权限。当前在运行的实际平台尚未重启。
3. **原始源表单位和年度证据核实未执行。** 不导入用户工作簿；页面继续明确提示未核实、禁源表金额图，不能把隔离样例当真实确认。
4. **真实保存/生成/报价联调未执行。** 继续遵守禁止触发真实任务和写实际台账的边界；不将 mock/隔离测试报告成真实业务运行成功。

有 finance 账号的回退不会自动成功。须先明确批准如何恢复这些账号所属部门，不能删除数据或静默改派后回退。隔离测试仅对合成账号执行显式恢复。

隔离 PostgreSQL 验证容器使用独立端口与 tmpfs，结束后按精确 ID 和任务标签核实清理；未连接实际数据卷或重启实际服务，[清理记录](implementation-evidence/finance-isolated-db-cleanup.json)。

本阶段当时结论：**SDD 代码实施及批准范围内隔离验证已完成；实际库迁移、真实财务接入和源表核实尚待处理，整体上线未完成。** 后续实际部署见第 9 节。

## 9. 本机实际环境部署与账号接入（2026-10-14）

### 实际交付与授权

用户在隔离验收后要求“需要整体上线”，并明确确认以下实际账号授权。所有操作使用原角色、权限与正常登录/绑定规则；没有修改文档、报价及其共用后端链路。

| 交付项 | 实际状态 |
| --- | --- |
| 总经理五入口、统一桌面布局、企业 Logo | 已加载业务前端构建产物；商机、文档、报价、知识、财务五入口在 1440×900 和 1920×1080 均通过。 |
| 售前填报 | `product_user` 仅 presales 台账编辑、提交、发布授权；真实 GET、空白新增表单和 GM 财务拒绝通过。 |
| 工程填报 | `engineering_user` 仅 engineering 台账编辑、提交、发布授权；真实 GET、空白新增表单和 GM 财务拒绝通过。 |
| 财务填报 | 新建 `finance_user`，Portal id 14，普通财务员工；仅 finance grant 的 can_edit=true，can_submit=false、can_publish=false。原本人精确版本发布规则以 can_edit、作者、最后修改人及精确 revision/checksum 判定，不借用通用整本发布权限。 |
| 财务身份与管理界面 | 实际平台 finance 枚举已生效，管理前端显示财务部/部门员工；正常登录、既有首次改密流程及原门户绑定通过。无 staff/superuser、其他模块或跨部门 grant。 |
| 总经理知识资料范围 | 原名单缺 manager_user（13），验收如实发现 403。用户明确批准后，仅在原 `PORTAL_PRODUCT_KNOWLEDGE_AUTHORIZATIONS` 为 13 添加与既有用户 10 相同的 3 个库、55 篇已批准资料。资料列表及原文预览 GET 通过；没有导入或知识库管理授权。 |
| 财务只读看板、精简 BI | 读取真实既有已发布数据；源表金额单位及年度保持“未核实”，不绘制不可信源表金额图，不补零。 |

知识授权使用原接口的逐用户资料范围；没有独立 HTTP read_only 开关，资料接口本身不提供导入或知识库管理。现有个人问答流程沿用，验收不新建会话或调用模型。新增 13 不改 1/10 范围及全局 authorization revision，避免使已有对话、蓝图知识证据失配；该决策遵守本轮共用生成链冻结，旧用户完整 scope 不变。

### 备份、迁移与服务加载

- 实际 PostgreSQL 目标为 `127.0.0.1:15432/aicompany_claw`。执行前完成 custom pg_dump，校验 pg_restore 清单；实际业务 SQLite 使用 SQLite 原子备份并 integrity_check=ok。备份、原 env、账号凭据位于忽略目录 `.runtime/enterprise/sdd-live-20261014/private`，限制为当前 Windows 操作员与 SYSTEM；公开证据不含密码或令牌。[备份证据](implementation-evidence/live-release-20261014/backup-preflight.json)。
- 实际执行 `alembic upgrade head`，revision 为 `20261014_finance_department`。唯一业务 DDL 是 users 部门 CHECK 增加 finance，Alembic 自建版本表；迁移时既有 9 个平台账号完整行相等，没有启动补列、补索引或管理员权限变化。[实际迁移](implementation-evidence/live-release-20261014/migration-result.json)、[日志](implementation-evidence/live-release-20261014/actual-migration.log)。
- 重载平台网关、管理前端和业务前端；业务前端使用既有 Vite preview 提供已构建 dist，沿用原 API proxy。`scripts/start-enterprise.ps1` 仅增加 dist 存在检查、改为 preview，后续同一启动入口保持部署方式。
- 知识名单仅启动读取，因此在批准资料授权后另外重载业务 Portal 以加载配置。没有重启模型网关或三个 Worker，没有改其模型、任务、计算、下载配置或代码。[Portal 配置重载](implementation-evidence/live-release-20261014/approved-portal-reload.json)。
- 最终五个服务健康，8080/8100/18411/3080/3081 各只有一个监听进程，进程命令/路径/启动时间与归属记录相符，三个 Worker 及模型网关仍为原进程。[最终服务核对](implementation-evidence/live-release-20261014/final-services.json)。

### 实际验证与证据

| 检查 | 实际结果 |
| --- | --- |
| 构建产物已部署 | HTTP 提供的 JS/CSS 与当前 dist 逐字节相等，Logo 与实施前 SHA-256 一致。[产物校验](implementation-evidence/live-release-20261014/served-assets.json)。两套构建、61/61 前端检查及隔离写入交互证据见第 8 节。 |
| 实际财务身份 | 正常登录/首次改密/绑定；capabilities 仅 finance，自己的台账 GET 200，售前与工程 GET 403，业务数据不变。[结果](implementation-evidence/live-release-20261014/finance-account-live.json)。 |
| 实际售前、工程授权 | 各自唯一所属台账 grant 与 GET 200，finance GET 403，正常绑定刷新；真实记录未改。[结果](implementation-evidence/live-release-20261014/department-grants-live.json)。 |
| 知识名单 | 仅增加已批准用户 13 的资料范围；其他配置、生成专用 retrieval grant 与旧用户知识 scope 不变。[授权证据](implementation-evidence/live-release-20261014/manager-knowledge-grant.json)。 |
| 实际桌面浏览器 | **14 组 PASS，20 张截图**：五入口×两种尺寸，三个实际员工台账/空表单/GM 拒绝，真实管理后台财务行；没有页面 JS 错误、意外业务 HTTP 错误或业务写请求。[结果](implementation-evidence/live-release-20261014/live-browser-results.json)、[日志](implementation-evidence/live-release-20261014/live-browser.log)。 |
| 实际知识只读浏览 | **1 组 PASS，2 张截图**：打开已有批准库、真实文档列表、已有原文预览 GET；不新建会话、不调用模型、不导入。[结果](implementation-evidence/live-release-20261014/live-knowledge-browser-results.json)。 |
| 真实业务数据 | 上线前后文档任务、工程任务、台账、版本、快照等 **8 张表的完整行和哈希相同**，没有新增真实生成/报价任务或改写台账。[核对](implementation-evidence/live-release-20261014/business-data-unchanged.json)。 |
| 后端冻结与既有改动 | 原 580 文件中 576 未变，4 个变化和 3 个新增均为已批准财务前置包；services 原有全部未提交文件及 Logo 保持。未授权后端差异 0；git diff --check 通过。[冻结核对](implementation-evidence/finance-backend-verification.json)。 |

浏览器业务读取透传真实服务；仅登录及必要原账号绑定使用原鉴权流程。业务写请求被验收拦截器禁止，自动 Agent SSE/ping 在验收中抑制，避免检查期间额外启动 Agent 或模型。此结果不代表已验证 Agent 运行状态或模型问答。财务截图中的服务初始化提示由该抑制产生。

验收失败记录保留：首次脚本误用新增按钮名称，第二次误用多个财务表格的单元素 locator，均只修验收脚本；第三次准确暴露知识 403，获用户批准补资料名单后消除。知识原文首轮的 Playwright service-worker 阻止钩子与无同源 sandbox iframe 冲突，移除测试钩子后原安全 sandbox 不变、预览通过。未屏蔽真实业务错误或修改后端以制造 PASS。

### 实际页面截图

| 页面 | 1440×900 | 1920×1080 |
| --- | --- | --- |
| 商机看板 | [截图](implementation-evidence/live-release-20261014/live-opportunities-1440.png) | [截图](implementation-evidence/live-release-20261014/live-opportunities-1920.png) |
| 文档生成 | [截图](implementation-evidence/live-release-20261014/live-documents-1440.png) | [截图](implementation-evidence/live-release-20261014/live-documents-1920.png) |
| 产品报价 | [截图](implementation-evidence/live-release-20261014/live-estimate-1440.png) | [截图](implementation-evidence/live-release-20261014/live-estimate-1920.png) |
| 知识检索 | [截图](implementation-evidence/live-release-20261014/live-knowledge-1440.png) | [截图](implementation-evidence/live-release-20261014/live-knowledge-1920.png) |
| 财务看板 | [截图](implementation-evidence/live-release-20261014/live-finance-1440.png) | [截图](implementation-evidence/live-release-20261014/live-finance-1920.png) |
| 售前填报 | [截图](implementation-evidence/live-release-20261014/live-product-entry-1440.png) | [截图](implementation-evidence/live-release-20261014/live-product-entry-1920.png) |
| 工程填报 | [截图](implementation-evidence/live-release-20261014/live-engineering-entry-1440.png) | [截图](implementation-evidence/live-release-20261014/live-engineering-entry-1920.png) |
| 财务填报 | [截图](implementation-evidence/live-release-20261014/live-finance-entry-1440.png) | [截图](implementation-evidence/live-release-20261014/live-finance-entry-1920.png) |

另有 [管理后台财务账号](implementation-evidence/live-release-20261014/live-admin-finance-account.png)、[批准资料列表](implementation-evidence/live-release-20261014/live-knowledge-documents-1440.png)、[原文预览](implementation-evidence/live-release-20261014/live-knowledge-original-1440.png)，三类空白新增表单截图在同目录。

### 访问、凭据与剩余边界

- 员工与总经理工作台：<http://127.0.0.1:3080/>；管理后台：<http://127.0.0.1:3081/>。本次部署目标是当前机器的实际环境；没有另行扩展 LAN 绑定或部署云端。
- 新财务账号 `finance_user` 的登录交接文件：`.runtime/enterprise/sdd-live-20261014/private/finance-login.txt`。密码不写入本文、公开日志或 Git；原其他账号密码保持。
- **真实写入及模型调用未验证**：保存、提交、本人精确发布及冲突用隔离测试验证；实际验收只读。没有导入真实工作簿、生成文件、运行报价或知识模型问答，不能将本次部署验收报告为这些真实业务任务已运行成功。
- **源表金额单位与月份年度未核实**：界面仍明确提示，未知不补零，源表金额图继续禁用；后续业务人员提供证据后再按原流程核实。
- **回退有财务账号门槛**：当前已存在 finance 用户，直接 downgrade 会按原迁移保护拒绝。不得删除或静默改派账号以绕过；需明确恢复计划和再次授权后操作备份或部门恢复。本轮没有回退实际库。

当前结论：**SDD 功能与获准最小前置包已在本机实际环境部署、账号接通并通过真实只读验收。禁止的真实任务、真实台账写入及未核实源表口径仍如实保留为未验证/待核实项。**

## 10. 少量代表性流程验证（2026-10-14）

用户要求只选择少量有代表性的项目，不全量验证。本轮执行 **3 个业务场景＋1 次旧版本冲突**，不重复全套测试；另对验收发现的长金额排版做定向修正、必要构建与两种桌面尺寸检查。

### 环境与范围

使用当前已部署构建页面、正常平台登录，以及实际业务 SQLite 的原子副本。单独启动原 Django 后端 HTTP 服务 `127.0.0.1:18102`，浏览器的业务请求转发给副本中同账号正常登录的门户 session，CSRF 验证沿用原规则。响应来自原后端，不使用 mock/fixture 返回数据。账号、角色、台账 grant 全部来自副本，未增加权限。

平台到门户的真实写入代理链本轮没有执行：业务写入仅落入隔离副本，实际环境保持只读。副本不启动 Worker、不开模型调用、不导入工作簿，生成/报价接口不在允许写入清单中。[隔离证明](implementation-evidence/representative-validation-20261014/isolation.json)。

### 结果

| 代表场景 | 结果与关键事实 |
| --- | --- |
| 售前原字段保存、提交、发布 | **PASS**。编辑一条已有源表记录，仅改项目进展；其余原字段逐项相等，共核对 21 个字段。台账从 v3→草稿 v4→提交 v5→发布 v6；保存、提交期间经理看板完整快照不变，发布后显示修改结果。 |
| 售前旧版本冲突 | **PASS**。保存后以旧 v3 再发 PUT，原后端返回 **409**；当前 v4 与完整记录不变，无覆盖。 |
| 工程未知进度与发布 | **PASS**。空进度仍空白，HTML 必填阻止保存请求，台账不变；明确填写合成验证值 **25%** 后保存、提交、发布，经理看板显示 25%，未知计划日期仍空白。 |
| 财务本人精确发布 | **PASS**。finance_user 仍仅 can_edit=true，无提交及通用发布权限；新增本人源表口径记录，不伪造来源。1 月金额保持空白，7 月明确测试零经原后端规范为 0.00，12 月计划回款为 10.00。草稿不进入经理看板；发布请求严格包含本人 UUID、draft_revision、checksum 及两个当前版本基线，经理看板仅新增本人选定的 1 条。 |
| 财务历史快照保留 | **PASS**。24 条原已发布记录逐项保持，归属未核实的历史记录复选框禁用。基线历史 record_meta 为空，因此不将本次测试表述为已验证“明确他人作者的发布权限”；这里只证明未知归属不可选及历史记录保持。 |

售前及工程成功请求和截图见 [第二次运行记录](implementation-evidence/representative-validation-20261014/second-attempt.json)；该次运行随后在财务数值格式断言停止。财务按原两位小数规范调整验收断言后，仅续验财务，不重跑已通过的售前与工程。[合并结果](implementation-evidence/representative-validation-20261014/results.json)、[最后日志](implementation-evidence/representative-validation-20261014/browser.log)。

首次售前断言误把修改字段的开头换行当作应保留内容，原后端会 trim；修正测试输入后用新副本重跑。上述两处均只修验收脚本，没有改变后端校验或金额规则。

### 发现及修正

财务看板在 1440 宽下，较长合同金额被 `overflow-wrap:anywhere` 拆成两行。仅修改 `frontend/src/business/finance/finance-board.css`：按卡片宽度缩放字体、禁止金额换行，极端长值允许局部横向滚动以保留完整数值。不做金额缩写、截断、补零或统计算法改动。

重新构建 **PASS**，保留原大 chunk 警告；当前 HTTP JS/CSS 与新 dist 逐字节一致，Logo 哈希仍一致。[构建](implementation-evidence/representative-validation-20261014/frontend-build.log)、[产物核对](implementation-evidence/live-release-20261014/served-assets.json)。

定向浏览器检查 **1440×900、1920×1080 均 PASS**：五个指标原文本完整，全部单行且无指标横向溢出、无整页横向溢出；未重跑全量测试。[布局结果](implementation-evidence/representative-validation-20261014/finance-layout-results.json)。

### 截图与结束核对

- [售前发布](implementation-evidence/representative-validation-20261014/presales-published.png)、[工程发布](implementation-evidence/representative-validation-20261014/engineering-published.png)
- [财务本人发布](implementation-evidence/representative-validation-20261014/finance-own-exact-published.png)
- [修正后财务看板 1440](implementation-evidence/representative-validation-20261014/finance-metrics-1440.png)、[1920](implementation-evidence/representative-validation-20261014/finance-metrics-1920.png)

以上均为实际库副本中的验证页面，不将合成记录当真实业务。

副本实际执行了台账写入和发布；文档、工程任务及其他 task/job 表与实际库相同，没有创建或执行任务。[隔离最终核对](implementation-evidence/representative-validation-20261014/final-isolation.json)。真实库 8 张业务表与上线前备份的完整行、哈希仍相同；原五个服务、Worker 和模型网关保持运行。后端冻结、Logo 与 git diff --check 通过。

隔离服务已按 PID/路径/命令/启动时间核实并停止，18102 端口释放；证据副本保存在原受限 private 目录。[清理记录](implementation-evidence/representative-validation-20261014/cleanup.json)。

本轮结论：**选定的三个业务流程与旧版本冲突通过真实后端 HTTP 的隔离验证，长金额排版已修正并部署。没有做全量验证，没有在真实台账保存/发布，没有触发真实生成、报价或模型问答。**

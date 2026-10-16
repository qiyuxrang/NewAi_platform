# 百川阁技术方案

版本 V1.4。本文件为本轮实现契约；以 [spec.md](spec.md) 的业务规则和 [acceptance.md](acceptance.md) 的实际结果为验收依据。

## 1. 现有工程证据与接入点

以下路径均相对仓库根目录，记录本轮实际接入点。工作区另有其他任务的修改，不能把全部 HEAD 差异视为百川阁改动。

| 已验证事实 | 证据位置 | 对应实现路径 |
| --- | --- | --- |
| 前端为 React/TypeScript，部门 feature 在现有路由分发 | frontend/src/App.tsx；frontend/src/pages/DepartmentWorkspace.tsx | 已登记百川阁 feature，沿用现有登录/路由守卫 |
| 产品功能白名单与总经理入口分别维护 | frontend/src/enterprise-navigation.ts | 已同时登记 departments.functions 与 managerEntries |
| 产品有独立侧栏，总经理分支避免重复产品侧栏 | frontend/src/business/product/ProductWorkspace.tsx | 共用百川阁内容，保留各自外壳、标题与图标映射 |
| 总经理图标按菜单名称映射 | frontend/src/components/Sidebar.tsx | 已补百川阁图标，详情时保持入口高亮 |
| 前端业务请求复用 Bearer 代理 | frontend/src/business/api.ts | /api/product/ 仍映射到 /api/enterprise/business/product/；仅扩展 ApiError 字段错误传递 |
| 现有代理注入 Portal 会话与 CSRF | platform/app/routes/enterprise.py | 复用现有代理，未新增百川阁专用代理或绕过身份的直连接口 |
| 后端按 /api/product/ 挂载业务 | services/business/backend/config/urls.py；portal/baichuan_urls.py | 已挂载 /api/product/baichuan/，复用允许的产品代理根 |
| product_user_allowed 复用模块授权，经理被现有部门授权判断覆盖 | services/business/backend/portal/product_service.py；portal/security.py | 仍为必要条件；百川阁另在 baichuan_service.py 执行范围确认及读写名单门禁 |
| 既有部署内共享台账、用户独立标记具有不同范围 | services/business/backend/portal/business_models.py；portal/tender_models.py | 百川阁按经确认的部署范围共享；创建人仅审计，不作为租户或 owner 过滤 |
| 现有编辑采用事务、预期版本、409 和字段审计 | services/business/backend/portal/hr_recruitment_api.py；portal/baichuan_service.py | 百川阁独立服务已采用事务、公司行锁及版本条件更新 |
| Django 测试已有业务基类 | services/business/backend/portal/tests/base.py | 百川阁服务及初始化沿用 PortalTestCase，在隔离测试库验证 |

既有工程未发现可直接复用的组织租户模型；新增 Company 是企业资料对象，不是账号租户边界。这不证明部署中所有账户必然属于同一组织。只有 D-03 确认后才能开放部署共享库，不能把 portal_user_id 身份绑定当成组织 ID，也未为跨企业场景新增多租户系统。

## 2. 边界与授权实现

读取须同时满足有效登录身份、既有产品模块授权、总经理或产品角色、已确认的部署共享范围和明确的读取名单；写入再检查维护名单。服务端返回 can_create、can_edit，前端据此呈现操作，服务端仍独立执行授权。

读写通过 baichuan_service.py 的统一授权判断，不因直调API而放宽；共享范围未确认时读写均拒绝，维护名单未配置时写入拒绝。详情对不可见或不存在公司统一返回404，不泄露对象存在性；其他认证、权限和服务不可用仍保留原链路语义。本轮未修改实际账号授权。

实现通过 `getattr(settings, "PORTAL_BAICHUAN_SCOPE_CONFIRMED", False)`、`getattr(settings, "PORTAL_BAICHUAN_READ_USER_IDS", ())` 和 `getattr(settings, "PORTAL_BAICHUAN_WRITE_USER_IDS", ())` 读取独立 Django settings，缺省全部拒绝。读取名单与写入名单不能替代既有 product_user_allowed 及角色要求，写入者也必须在读取名单中。本轮只在隔离测试 settings 中覆盖这些值；真实环境须待 D-02/D-03 确认后明确配置。本功能未在 settings.py 注册同名环境变量解析，单独设置环境变量不代表授权生效。

本功能新增独立模型、服务、接口及页面；不改文档生成、报价计算、知识检索、招标采集、Worker、提示词和已有台账发布规则。历史 SDD 的冻结条款按其原任务范围理解；本功能也不得借共用修改间接改变这些链路。当前工作区存在其他未提交修改，实施证据需比较任务开始时的快照而非将全部 HEAD 差异算成本任务。

## 3. 数据模型

已在 baichuan_models.py 实现三个模型，由 models.py 注册发现并配套迁移；使用现有 Django 数据库，不增加数据库服务。类别及等级使用固定枚举，无资质字典后台。

| 对象 | 最小字段 | 约束 |
| --- | --- | --- |
| Company | UUID id，name，credit_code，province/city/address，website，phone，contact_name/contact_phone/email，description，source，verified_on，version，created_by/updated_by，created_at/updated_at | name 必填；空信用代码归一为 null，非空信用代码在确认的数据范围内唯一；名称不强制唯一；version 初始1 |
| CompanyQualification | UUID id，company，category，status，grade，certificate_no，valid_until，source，verified_on | 同条记录绑定类别、状态、等级；UNKNOWN/ABSENT 不带等级，labor 不带等级；允许同类多份正面证书，矛盾状态报错 |
| CompanyPerson | UUID id，company，name，department，position，reports_to_text，specialties，credentials，achievements，source，verified_on | 有人员记录时姓名必填；汇报关系仅保存有依据的文本，不推导树或制造关系 |

公司内部 ID 负责关联，不用名称、Excel 行号或创建人作为长期归属。人员姓名不作为跨企业唯一键。复用既有 audit 记录动作、目标和变更字段名，不将完整电话或人员资料写进通用日志。

同类多条 PRESENT 记录按证书区分；完全相同字段的资质记录以及同类别重复证书号会被拒绝，同类别不能混存不同具备状态。非空信用代码校验18位允许的大写字母/数字并由数据库唯一约束保护，不声称已核验真实企业身份。公司级事务、公司行锁和预期版本条件更新防止并发覆盖；版本冲突返回409。索引限于信用代码、公司关联、类别/状态/等级组合和稳定排序，没有全文搜索或缓存。

## 4. 查询算法

1. 从当前授权数据范围取得公司集合。
2. 名称用现有数据库能力做包含匹配，用户输入作为参数，不拼接SQL。
3. 对每个已选类别添加独立的 EXISTS：company 相同、category 相同、status=PRESENT；指定等级时 grade 必须在该类选中集合内，any 时不限制等级。
4. 多类别 EXISTS 之间取 AND。不能对同一 join 简单堆叠互斥 category，也不能跨记录拼接类别与等级。
5. EXISTS 保持公司集合不被子记录扩增，计算 total 后稳定按 name/id 排序和分页。列表预取资质，不加载完整人员和长简介。

排序不表达企业实力。数据未知、证书到期与人员能力不暗中改变过滤口径。

## 5. 接口与 DTO 契约

后端业务根：`/api/product/baichuan/`，由 baichuan_urls.py / baichuan_api.py 实现。前端向既有 apiRequest 传该业务地址，浏览器实际访问 `/api/enterprise/business/product/baichuan/`；沿用原 JWT → Portal 会话及 CSRF 代理。`frontend/src/business/api.ts` 仅扩展 ApiError 的可选 `errors` 字段，筛取服务端字符串字段错误，保留原三参数构造方式及原请求、鉴权、上传下载语义。

| 方法与路径 | 行为 |
| --- | --- |
| GET companies/ | 列表、总数、分页、查询回显及创建权限 |
| GET companies/{id}/ | 公司完整详情、version 和编辑权限 |
| POST companies/ | 创建公司及提交的资质、人员；一次事务保存 |
| PUT companies/{id}/ | 提交完整资料快照与 expected_version；原子更新 |

本期没有删除公司和 Excel 上传 HTTP 接口。无需为静态七类字典单独开发后台管理API；前后端字典一致性由检查保证。

查询参数：q（公司名称）、page（默认1）、page_size（默认20、最大100），以及七类代码。类别值为逗号分隔的精确等级，或单独 any；不出现代表不限。重复参数、未知类别/等级、any 与具体等级混用、labor 指定等级、非正整数分页均返回明确400，不静默忽略错条件。

查询示例，表示电子与智能化一级或二级，且 CMMI 三级：

```text
GET /api/product/baichuan/companies/?electronic=1,2&cmmi=3&page=1&page_size=20
```

列表响应的最小结构：

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 20,
  "has_more": false,
  "query": {"q": "", "filters": {"electronic": ["1", "2"], "cmmi": ["3"]}},
  "permissions": {"can_create": false}
}
```

items 中每家公司提供 id、name、province、city、主要联系方式、已录入资质摘要、matched_qualification_ids。完整人员与长简介从详情读取，不从列表摘要反向保存。

详情 DTO 为 `{company, qualifications, people, permissions: {can_edit}}`。company 包含完整业务字段、id、version、created_at、updated_at；两个子数组逐条包含 id 及各自业务字段。日期为 YYYY-MM-DD 或 null；系统时间为带时区ISO时间。写入响应采用同一详情结构，另带 warnings；发现同名公司时返回 duplicate_name 提示，不自动合并。前端类型、字典与草稿转换位于 Baichuan-data.ts，只从完整详情生成编辑快照，不把只读系统字段回传。

PUT 写入快照示例：

```json
{
  "expected_version": 1,
  "company": {"name": "验收样例A", "credit_code": null, "province": null, "city": null, "address": null, "website": null, "phone": null, "contact_name": null, "contact_phone": null, "email": null, "description": null, "source": null, "verified_on": null},
  "qualifications": [{"category": "electronic", "status": "PRESENT", "grade": "1", "certificate_no": null, "valid_until": null, "source": null, "verified_on": null}],
  "people": []
}
```

POST 必填 company.name，其他公司字段和两个子数组可省略，不要求 expected_version；新公司 version=1。PUT 要求正整数 expected_version、完整 company 业务字段及两个子数组，漏字段会报错，不能默认为清空。子记录已存在时提交其 id；新记录无 id；子记录 id 必须属于该公司。显式移除子项在前端保存前确认；合法快照一次事务提交，编辑成功 version 增1并返回完整最新详情。

| 情况 | 约定响应 |
| --- | --- |
| 输入或等级不合法 | 400，code=invalid_request，detail 与字段级 errors |
| 认证失效/无权 | 沿用认证与代理语义；401/403 分别呈现，不改为200空数据 |
| 公司不存在/不可见 | 404，避免暴露其他范围对象 |
| 非空信用代码重复 | 409，code=duplicate_company，不静默合并 |
| 预期版本过期 | 409，code=version_conflict，保留本地输入，不自动覆盖 |
| 请求失败/业务断连 | 沿用现有失败处理，保留查询或编辑内容 |

同名疑点在页面保存前提示核对，名称本身不设全局唯一约束。同名不同信用代码允许分别存在。官网用原生URL解析及服务端白名单协议检查；不因新功能取消既有认证、CSRF或错误处理。

## 6. 前端状态与参考图落实

已在现有 product 目录实现 Baichuan.tsx、CompanyDetail.tsx、CompanyEditor.tsx、Baichuan-data.ts 和 Baichuan.css；API 调用复用 apiRequest，没有新增请求客户端或通用筛选引擎。

主路由为 `/departments/product/baichuan`，详情用 `?company={id}`，搜索、资质和分页保留于URL，列表右侧正文滚动位置按查询保存在 sessionStorage 并在返回时恢复。两个入口复用同一 feature，无总经理专用数据副本。查询参数不包含电话等敏感资料。

按参考图使用一排七类下拉；菜单里是多选 checkbox，而非普通单选 select。每个控件展示不限/具备即可/该类合法等级，选择即时更新；Escape 与外部点击关闭但不重置。全局重置同时清空名称、资质并回第一页。弹层开启时合理管理焦点，避免被面板overflow裁切。

文字搜索使用 Enter 或搜索按钮提交；资质变化即查询。AbortController 与当前响应标识共同阻止旧成功/失败覆盖新条件。首屏、更新中、失败、空结果分开呈现；请求未结束时不把旧数据标成新结果或提前显示0家公司。

列表标题、副标题、四列表头、搜索和重置、白色面板与固定导航按图。唯一明确的业务替换是“导入 Excel”→“新增公司”；用户未授权的其他菜单增删不纳入本次。详情、编辑复用相同视觉与既定字段，不把缺少独立截图视为可编造资料的理由。

按参考图比例在1440×900、1920×1080的PC视口检查；没有手机端。保留原工作台固定外壳，只有右侧业务正文滚动。新增编辑使用可滚动的宽表单弹窗，保存操作可达，并提供未保存改动退出确认。

详情采用同一右侧内容区：顶部为返回、公司名称、地区、官网首页和有权限时的编辑按钮；正文分为“基础资料”“企业资质”“联系方式”“公开人员资料”四个白色区块。基础资料展示简介、信用代码、地址、来源与核实日期；资质逐条展示类别、等级、可用的证书编号/有效期及来源，命中项另有文字标识；联系方式优先呈现业务联系人和业务电话，再列公司电话与邮箱；团队逐人呈现岗位、部门、专业、认证、成果及来源，有明确汇报关系才显示关系文本。默认不生成组织树。资料缺失按字段表达，不用整页空态掩盖其他已知信息。

新增/编辑使用宽表单弹窗，按“基础资料与联系”“企业资质”“核心人员”分组。公司名称为必填，其余可补充；七类资质分别选择未知、不具备或具备，具备后按类别选择等级或等级待补充，劳务不显示等级。支持同类增加多份证书；每份证书保留自身等级及来源，不能压成一个覆盖旧值的单选字段。人员按条新增/修正，可填写已知汇报对象文本；明确移除资质/人员时在保存前提示。页尾为取消与保存，保存中防止重复提交；字段错误就地提示，网络错误保留完整草稿，版本冲突提示重新获取并人工核对，不自动覆盖。来源日期与系统修改时间分别展示。

## 7. 一次性初始化方案

已实现 `portal/baichuan_import.py` 和管理命令 `import_baichuan`，不提供长期导入界面。使用 Python 标准库 ZIP/XML 只读解析 XLSX，无新增生产依赖，也未把模板制作工具带入运行时。支持共享字符串、内联文本及Excel日期；公式、错误值、无法保真的数值型信用代码/电话和未映射非空列均报错，不执行公式、不访问外部链接。输入大小及解压大小有上限；结构错误拒绝执行，不静默丢弃重复行或单元格。

预检默认零业务写入，输出输入 SHA-256、完整字段映射及映射 SHA-256、source_rows 的来源表/行与输入值、records 的标准化内容及固定UUID、内容摘要、归属判定、异常与冲突、预计新增/跳过/拒绝数。空白模板的企业与人员数据区实际均为0条，不生成假公司。报告逐字段收集非法数据，保留待处理项，不能把部分有效行先写入。

公司名称必填；信用代码为强识别依据，无代码时按预检确认映射归属，不凭同名自动合并。人员通过主表公司名称和可选信用代码定位，无法唯一归属即报孤立或歧义，保留异常供人工处理。只有经确认的无错误清单才能 apply。

列名和归属差异通过 `--mapping` JSON 处理，报告内也保存同一映射：

| 映射字段 | 含义 |
| --- | --- |
| company_sheet / people_sheet | 企业与人员工作表名称 |
| company_columns / people_columns | 原表头到已支持业务字段的显式映射；未映射非空列阻断，不能直接舍弃 |
| company_links | `工作表:行号` 到现有公司UUID；必须人工明确指定且业务内容一致，只关联和核对快照，不覆盖既有来源；原表来源保留在清单与回执 |
| people_links | 人员来源键到主表公司来源键，显式限定归属候选；不能凭重名自动合并 |
| notes_reviewed | 来源键到原备注全文，表示已人工逐项核对；非空备注未获同文确认就阻断，原文继续保留 |
| qualification_overrides | 公司来源键到完整的规范化资质数组，用于原列多等级或备注多证的人工归一 |

`qualification_overrides` 是该公司整份资质数组的替换来源，条目仍须通过同一服务端类别、状态、等级、证书及日期校验。提供明确覆盖时不再先自动解释原列的“一级、二级”等多值文本，source_rows 仍保留原值。原行所有非空资质类别都必须在覆盖数组中出现，包括 UNKNOWN/ABSENT；空数组或遗漏类别报 incomplete_qualification_override，不能在处理电子资质多等级时丢掉同一行的其他资质。备注中的多份证书须人工逐条归一，notes_reviewed 不能替代资质明细核对。

人工核对无错误预检报告后，将其复制为受控清单并设 `confirmed=true`；不能直接修改 records 来绕过输入或映射核验。apply 必须提供 `--manifest`、`--actor` 和 `--report`，操作人须为现有有效账号并通过同一百川阁维护权限。未传 `--mapping` 时使用清单内映射；显式传入时仍须与清单指纹一致。以下为已实现的调用方式，真实执行仍需 D-02/D-03/D-04 及目标环境确认：

```text
python manage.py import_baichuan --input initial.xlsx --dry-run --report preview.json
python manage.py import_baichuan --input initial.xlsx --dry-run --mapping reviewed-mapping.json --report preview.json
python manage.py import_baichuan --input initial.xlsx --apply --manifest confirmed.json --actor 已确认维护者用户名 --report result.json
```

初始化复查文件、映射、清单内容和目标资料状态，在整批数据库事务内创建稳定UUID的公司及子记录并记录来源/操作审计。已有对象按清单核对版本、全部业务字段和子项ID/内容，完全一致才跳过，内容已被网页维护则报冲突，不用旧Excel覆盖。清单预先固定ID和摘要，同一文件、映射及来源行重跑无需依赖提交后的回执，因此提交后回执丢失也不会重复创建。

数据库操作失败时整批回滚；事务提交后才写回执，含创建/关联/跳过对象ID及内容摘要。回执采用临时文件后替换，报告路径不能覆盖输入、映射或确认清单。若回执文件写入失败，命令明确报告“数据库已提交，回执未生成”，须保留原确认清单恢复核对或重跑，不能宣称数据库已回滚。无需常驻导入批次表；指纹、映射、清单和回执作为受控运维资料保留，不提交真实联系人原表或报告到Git。本轮命令功能只对空模板和隔离工作簿验证；真实名录已提供，正式初始化清单仍待资料核对。

## 8. 实际改动范围与验证

已新增百川阁模型/迁移、service、api/urls、初始化解析与管理命令、测试及前端组件。现有文件增加必要注册：config/urls.py、portal/models.py、enterprise-navigation.ts、Sidebar.tsx 和 ProductWorkspace.tsx；DepartmentWorkspace.tsx 沿用原有分发，无需修改。business/api.ts 仅扩展字段错误传递。复用既有 API 代理及共用身份链，没有为百川阁新增绕过入口。

验证使用隔离SQLite和虚构账号/公司，既有库与真实账号授权不变。已执行新迁移检查、Django检查、服务/API及初始化测试（含并发版本冲突、事务回滚和回执恢复），结果及运行环境保存在 [backend-tests.txt](evidence/backend-tests.txt)、[backend-checks.txt](evidence/backend-checks.txt)。可复核命令为：

```powershell
# 仓库根目录；脚本清理真实库环境变量并使用独立测试库
powershell -NoProfile -File doc/baichuan-sdd/evidence/backend-command.ps1
```

前端已执行百川阁定向测试、全部既有前端测试和生产构建，结果见 [frontend-tests.txt](evidence/frontend-tests.txt)、[frontend-regression.txt](evidence/frontend-regression.txt)、[frontend-build.txt](evidence/frontend-build.txt)。定向命令为：

```powershell
# 仓库根目录
node --test frontend/tests/baichuan.test.mjs frontend/tests/manager-workspace.test.mjs frontend/tests/product-layout.test.mjs

# frontend 目录
npm run build
```

已执行隔离浏览器验证，覆盖双入口、PC视口、多选、查询与返回、详情官网、新增编辑、输入保留、权限和错误状态。浏览器使用实际 React、现有 JWT/Portal 代理及 Django/CSRF 链，仅以隔离虚构身份和数据库运行；无关服务状态与外部示例官网做隔离替代。步骤、日志及截图见 [browser-run.txt](evidence/browser-run.txt) 和 [browser](evidence/browser/)，代理回归结果见 [bridge-tests.txt](evidence/bridge-tests.txt)。通过数量与具体状态以这些实际输出及 acceptance/tasks 为准，构建不能代替浏览器或真实身份验收。

真实企业名录已于2026-10-16提供。该表为“总表＋七类分表”的重复视图，标题第1行、表头第2行、一行一项资质；不能原样作为目标一行一公司的初始化模板执行。先在业务库外只读提取、核对总分表、规范名称、保留来源行并提交候选等级映射；确认主体和疑点后再生成目标模板及正式预检清单。外部检索补充单独保留来源网址、日期、电话用途与原页/摘要核验程度，不覆盖原表。旧字典遗漏的CS1按新增全覆盖要求补入同一类别；CCRC服务范围不明确及劳务A/AAA等描述保留原文，不映射成其他资质或等级。详见 [资料核对记录](data-source-review.md)。

用户后续确认两类工作台均可维护，已在本机现有部署完成备份、0044迁移、真实全量初始化及portal8100重启，实际证据见coverage-deployment-result.json和coverage-live-results.json。不能把隔离测试夹具导入当作真实建库完成，也不能将已完成的本期定向回归表述为所有未覆盖业务链路均已验收。

## 9. 真实源表全量接入

复用既有公司、资质、人员字段与一次性导入事务，不新增抓取服务或通用数据框架。新增离线转换命令prepare_baichuan_source，将业务库外的结构化源表与补充证据转换为标准行JSON和显式qualification_overrides映射；工具生成标准中间工作簿后，仍走import_baichuan的预检、指纹、整批事务、重跑及版本保护。转换不等于确认正式导入清单。

每家公司简介保留全部原始资质声明及源行，来源字段保留电话用途和全部补充证据、URL、日期及核验程度；公开人员逐条关联公司。电话超出短字段时仅按完整号码边界选择展示值，全文在来源保留。未知当前状态及日期不补造。CS一级通过0044增量约束迁移纳入1～5级；不回写0042历史迁移。

正式授权使用环境配置PORTAL_BAICHUAN_SCOPE_CONFIRMED、PORTAL_BAICHUAN_READ_ROLE_CODES/READ_USER_IDS、WRITE_USER_IDS/WRITE_ROLE_CODES，默认仍为空/关闭。读写角色仅接受已有总经理与产品角色且保留模块检查；查看和维护独立配置。用户已确认两类工作台均可新增编辑，本机显式配置读写角色general_manager/product，不自动应用至其他部署。

全量验收在独立SQLite、现有API代理与React真实浏览器中进行：遍历服务端分页比较全部1283名称；逐公司检查1462原始声明与289证据无丢失；校验人员归属；核对CS1精确和组合筛选、详情返回、官网/来源链接、安全性及两个PC工作台布局。正式部署另留真实账号/库验收状态，不能用本轮隔离结果覆盖。

正式目标为当前项目services/business/.runtime/portal.sqlite3；0043已存在，仅新增执行0044。在线SQLite backup及local.env备份保存在私人目录local-deployment-20261016-113713。标准中间表由artifact-tool生成，指纹见正式回执。预检1283家公司/112人员、零错误；事务写入1460分类资质，同时保留1462原始声明。重复执行新增0、跳过1283。用户/角色/模块行指纹及其他业务表计数未变。仅portal8100重启加载新权限，8080/3080复用既有进程。

真实浏览器使用已有manager_user/product_user的正常HTTP登录及既有JWT、Portal会话、CSRF代理，无API替代、无测试公司写入；HR既有账号返回403。两账号分别遍历14页API并比较全部1283名称，实际页面检验65页末页3家。来源超过300字原生折叠，完整原文和链接可展开。来源的资料日期与已读/摘要程度仍显式保留。


## 追加实施：页面精简与官网补充（FR-22）

复用CompanyDetail现有字段和safeWebsite。展示层过滤空字段，移除信用代码/核实日期/修改时间的详情渲染，原始导入说明归入底部原生details，来源全文及HTTP(S)链接保留；有业务简介才显示简介。既有编辑数据快照和数据库字段保持可维护，不增加新字段/迁移。列表公司名22px，适度扩大首列，长名换行，实际浏览器检查1440/1920两种外壳。官网按钮沿用右上已有入口，同时显示可点击网址；没有网址就不渲染。资料补查独立只读进行，经主体与原页证据审核后，先备份，再以现有save_company权限、expected_version和原子事务更新已存在记录，完整保留资质、人员和旧来源；不新造公司或变更授权。


最新详情图覆盖前述纵向布局：CompanyDetail在现有CSS中采用企业展示卡、官网侧卡及约3:2双栏信息网格；图标复用lucide-react，中性CSS楼宇装饰不声称是企业实景，不新增图像服务/依赖。业务领域从简介中显式“业务领域：”行拆分，仅用于展示；详情API和数据库不变。官网复制复用浏览器Clipboard，成功/失败反馈与实际结果一致。参考图中的企业Logo和资质不复制到不匹配企业。


FR-23列表复用现有table、lucide企业/电话/外链图标和API website字段。list_companies仅在已有公司列选择加入website，无迁移、不改过滤授权。多号码以原生details展开，不生成联系人归属；页码/页长写URL并沿用取消过期请求及返回恢复。保留既有上一页/下一页可访问名称。


详情字号通过bc-company-detail作用域调整，不改变其他业务或工作台；联系标签列适度加宽，长地址换行，不固定卡片高度。最终浏览器验收附计算样式和两宽度截图。


FR-24：复用CompanyDetail与既有CSS，在同一网格中按overview/qualifications及business/contacts显式定位并按行对齐；不再使用互不对齐的嵌套列。参考图裁切的本地图片随前端构建，不增加图像服务/外部请求/依赖；assets/baichuan/source.json留存来源指纹和裁切坐标。纯装饰图使用背景或空alt；品牌标识严格绑定匹配公司，不触及数据库。资质及业务图标复用lucide-react；缩略图只装饰实际已录入的业务项。无数据不添加假卡片、假官网或评级。以真实平台两身份、两宽度及凯笙/万邦详情验证统一结构、行对齐、字号、装饰加载、来源/人员完整及无横向溢出；定向测试与构建通过后更新实际状态。


FR-25复用CompanyDetail顶部官网区域、safeWebsite、现有onEdit和完整表单；不增路由/API/数据字段。官网区域始终呈现访问按钮，有地址渲染安全a，无地址渲染disabled button并按维护权限提供添加地址入口。复制按钮及网址仅有合法地址时呈现。查询万邦官网另留原页与主体匹配证据；无法确认时保持空值，不能用同名企业或第三方介绍页填充。


FR-26复用全部规范公司名/既有检索原文，按428/428/427三批独立只读补查，各批仅写Git外研究目录。主代理核对一手原文、主体、字段语义及来源后串行整合，不新增数据库模型/导入界面/服务。真实库先在线备份，读取完整快照，再沿现有维护API传完整company/qualifications/people和expected_version；只补已审事实并追加来源，版本冲突停止该条、保留预检输入，不强制覆盖。保存前后核对公司全集、原资质、人员、账号权限及原始来源；研究覆盖台账与实际事实和更新收据分开统计。

FR-26实施核对：复用三个独立只读分片，另做原文独立审查；有争议集团/栏目页不填官网，投诉/培训/招聘/历史合同号码不追加为合作总机，公开人员保留原报道时任含义。既有非空官网/地址/邮箱/业务简介不覆盖，电话去重追加且不超过原字段长度，全部事实及用途在折叠来源保存，源表声明原文转存来源。字段更新通过已有网关API及完整快照完成，无模型/迁移/依赖变更。保存前发现三核心服务已停止，复用原启动器的进程归属/去重逻辑恢复8100/8080/3080，健康与实际鉴权通过，未启动或修改其他任务worker。


FR-27：基于真实库缺项快照与全部公司名称分三批独立补查；每家公司独立查询，读取原页、核对主体与联系方式角色。各研究代理只写Git外round2独立目录，分批不可变事实检查点；主代理统一审查、备份后调用现有完整快照+expected_version接口串行追加，资料新增后复核页面与覆盖指标，不改授权、数据库模型或导入方式。次级登记来源保留来源层级及角色时点，不以搜索摘要代替原页。


FR-28：复用website地址，Company增加一个有界website_kind枚举字段及增量迁移，既有公司默认corporate，列表与详情API一起返回；服务端校验类型，旧请求缺少类型时保留当前值，新增旧请求默认corporate。前端共用类型字典，列表/详情明确标签与访问动作，原编辑表单新增类型选择，保留完整快照与版本。迁移与部署由主代理单独处理，真实迁移前在线备份及隔离测试；不引入额外框架或类型推断。

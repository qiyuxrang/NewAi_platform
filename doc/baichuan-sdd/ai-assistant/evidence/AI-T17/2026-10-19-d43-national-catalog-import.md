# AI-D43：全国名录追加与侧栏改名

2026-10-19，用户要求将全国资质企业名录加入现有平台，并将侧栏“百川阁”改为“企业资质库”；随后明确不查询官网、不做外部真假核验，直接按现有页面结构导入。本轮按该最新授权执行，覆盖历史前端菜单冻结和只做首次初始化的范围限制；未增加日常导入界面、重建企业库或推送外部仓库。

## 实际接入

目标为现有3080前端、8080代理、8100业务及`services/business/.runtime/portal.sqlite3`。原库在线备份到本机私有目录，quick_check通过；原Excel另存等字节副本，SHA256为`d5f0a39e81bc741d2c6b1e245216e94e15eb90e13c807fd6f1ad7aa82dcf1849`。没有使用13180历史库、公开快照或虚构企业。

| 项目 | 实际数量 |
| --- | ---: |
| 源表资质记录 | 55,057 |
| 源表归并企业 | 47,400 |
| 关联原有企业 | 632 |
| 新增企业 | 46,768 |
| 原库企业保留 | 1,283 |
| 当前企业总数 | 48,051 |
| 新增可映射资质声明 | 55,055 |
| 仅来源保留的声明 | 2 |
| 原资质 / 原人员保留 | 1,460 / 125 |
| 当前资质声明总数 | 56,515 |

六表分别为电子与智能化36,930、CS 3,742、CMMI 2,368、CCRC 1,038、ITSS 8,462、安防2,517；“核验入口”不是企业表。名称仅按空白和全半角括号归一；原企业ID和名称保持。原表中同名多资质、多等级按来源逐行保存，未选最高等级或覆盖旧等级。电子表信用代码不写成证号；研发部门等非编号文本留来源。来源平台链接不当作企业官网，源表核验日期不写成系统已核实日期。

CCRC安全运维未公示、ITSS通用要求两条未对应现有安全集成/运行维护范围，全部原文追加到对应旧企业的资料来源，可在页面展开查看；原来源前缀逐字保持。没有把它们编造成某个精确等级或丢弃企业。源表的有效、年审、复评、历史名录等状态原文保留，不宣称已核实当前有效性。

## 实际改动文件

- `frontend/src/enterprise-navigation.ts`：产品/总经理菜单名称。
- `frontend/src/business/product/ProductWorkspace.tsx`：产品内侧栏名称。
- `frontend/src/components/Sidebar.tsx`：总经理菜单图标映射键。
- `frontend/tests/baichuan.test.mjs`、`department-assistant.test.mjs`、`manager-workspace.test.mjs`：既有菜单期望更新。
- `services/business/backend/portal/baichuan_national_import.py`：复用现有XLSX值读取、名称归一、字段校验及服务端维护权限；新增预检、稳定ID、事务增量和重放核对。
- `services/business/backend/portal/management/commands/import_baichuan_national.py`：默认只读预检；显式apply使用确认清单及已有维护者，报告私有保存。
- `services/business/backend/portal/tests/test_baichuan_national_import.py`：隔离行为检查。
- 本开发包README、规格、方案、任务、验收、进度和检查点：同步AI-D43范围与实际证据。

未修改现有路由、页面布局、列表标题、助手行为或业务权限。沿用现有依赖，无迁移、无新框架。本轮没有重启服务；现有3080预览服务加载重新构建的前端资源。工作区并行招标业务及上轮助手改动保留，不计为本任务改动。

## 实际执行的检查

1. 独立只读审计完整遍历六表，55,057行和47,400规范名与解析器一致；仅本地格式/映射检查，未访问来源网址。
2. 最终隔离后端16/16通过、0跳过，10.586秒；覆盖预检零写、字段映射、原值保护、源追加、版本CAS、过期编辑拒绝、权限、变更目标/输入拒绝、事务回滚和重复执行零写。仅内存SQLite，0模型/0网络。
3. 源追加补丁前，完整真实附件在空内存库导入47,400企业/55,055资质并重放，0重放写SQL，45.063秒；这是当时实现的容量证据，补丁后以本轮真实目标导入、16项检查及原资料核账为准，不冒充重新执行容量测试。
4. 前端既有导航/企业库相关25项全部通过；TypeScript、修改文件ESLint、Vite构建通过。仅有既有大chunk提示。
5. 主代理核对最终清单与独立审计一致后，使用既有维护身份执行单事务导入：46,768企业、55,055资质、632旧企业版本递增；2个旧来源只追加，其他公司业务字段、全部旧资质和人员不变。
6. 主代理独立以openpyxl逐行检查来源sheet/row/name/grade，55,057源行和47,400名称均有实际落库归属；原Excel与私有副本SHA保持。数据库quick_check通过，foreign_key_check为空；既有账号密码、角色和模块权限保持。正常重新绑定业务会话使2个账号last_login更新，未冒充全用户表字节未变。
7. 同一已确认清单在真实目标库再次执行：0新企业、0新资质、0版本更新、0来源追加，database_status=unchanged。

## 真实页面证据

两种角色均使用当前3080 Chrome实际页面，保留各自工作台外壳，侧栏显示“企业资质库”。共18组记录：产品全部六类筛选、同类OR、跨类AND及全库总数，经理全库与AND；均以当前SQL完整计数和首20条ID/名称对账。两角色均实际勾选一级和二级、翻页、查看详情、返回和原生刷新；新企业上海邮电设计咨询研究院展示六类原表资质及来源。两条仅来源声明在两个角色详情中均实际展开显示；全库第2403页实际11行，下一页禁用。无pageerror及横向溢出，无企业编辑或模型调用。

| 筛选 | 当前SQL与页面相同的企业数 |
| --- | ---: |
| 全库 | 48,051 |
| 电子与智能化精确二级 | 28,664 |
| CS精确二级 | 2,808 |
| CMMI精确三级 | 2,207 |
| CCRC精确二级 | 257 |
| ITSS精确二级 | 956 |
| 安防精确二级 | 496 |
| 电子一级或二级 | 37,055 |
| 电子二级且ITSS二级 | 128 |

私有证据根`.runtime/enterprise/national-import-20261019/`：`audit-independent/REPORT.md`与`audit.json`、`importer-tests/receipt.json`、`full-scale-receipt.json`、`backup-receipt.json`、`preview-final.json`、`confirmed.json`、`apply-result.json`、`replay-result.json`、`preservation-result.json`、`frontend-checks.json`、`browser-result.json`及`source-only-browser-result.json`。实际截图为`product_user-list.png`、`manager_user-list.png`、两角色`-new-detail.png`/`-source-only.png`和`product-last-page.png`；主代理已查看产品列表与经理新企业详情。

可重跑维护入口为上述管理命令；本机环境加载包装`run-command.py`明确断言目标库。`verify-preservation.py`、`verify-pages.py`和`verify-source-only.py`保留实际检查。首次隔离测试及容量夹具缺少完整授权的失败日志保留；首次保护脚本未排除正常last_login更新而失败，修正核账范围后逐字段通过，未为测试修改账号状态或回滚其他业务。

## 交付边界

本批47,400个规范企业全部在现用库可检索；功能与当前本机页面验收完成。按用户要求没有查询官网、外部真假验证或补齐缺失电话/官网/人员；新增企业这些字段保持空值，已有值保留。未对新增48,051规模的AI助手、复杂语言、导出及所有其他业务作全套回归，不以本次列表验收覆盖上轮助手范围。未执行远程部署或GitHub上传，原附件/完整业务库及运行凭据保持本机私有。

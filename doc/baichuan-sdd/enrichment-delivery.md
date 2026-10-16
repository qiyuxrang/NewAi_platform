# 全库补查交付记录

2026-10-16，SDD V1.6。用户确认范围为全部企业，选择使用企业尽调技能的主体识别、来源核对及公开资料查询部分。本轮完成全部1283家的一轮核对及确认事实保存；不能据此声明全部企业每个字段都齐全。

## 实际完成与文件

共用详情顶部统一“访问企业官网”按钮：合法HTTP(S)地址安全新标签打开，无地址禁用；维护者可通过“添加官网地址”进入原编辑表单。网址及复制仅在安全地址存在时展示，缺项不铺“未查询”提示。

实际前端文件：`frontend/src/business/product/CompanyDetail.tsx`、`frontend/tests/baichuan.test.mjs`、`frontend/tests/baichuan-browser.py`。复用前轮Baichuan.css及本地装饰图；本轮无新框架、模型、迁移、API或数据库重置。SDD的README/spec/plan/tasks/acceptance/delivery同步更新，新增本报告与official-button/enrichment检查证据。研究事实及真实公司清单保留在Git外私人目录，没有把敏感业务全量表提交仓库。

三批台账分别428/428/427，1283公司ID及名称全集一致。503条原页候选事实经主体/用途复核，19条拒绝或暂缓，484条追加入114家已存在公司来源。实际业务字段变化如下：

| 项目 | 本轮实际变化 |
| --- | ---: |
| 官网地址 | 54家新增 |
| 公司地址 | 54家新增 |
| 邮箱 | 44家新增 |
| 简介/明确业务领域 | 87家补充 |
| 电话 | 12家补充 |
| 公开人员 | 13条新增，保留报道时任属性 |

公司业务字段共251处变化。既有非空官网/地址/邮箱/实用简介不覆盖，电话去重追加；重复人员不重建。原始导入声明、旧来源、全部1460资质及112人员保留，人员现125条；1169家未更新公司逐行相同，用户/角色/模块逐行相同。保存前在线备份，使用manager_user正常鉴权与expected_version API逐条原子保存，没有写入测试公司。

## 实际执行的检查

| 检查 | 本轮结果/证据 |
| --- | --- |
| 前端定向 | 19/19，通过；evidence/official-button-tests.txt |
| 类型、局部ESLint、Vite构建 | 通过；evidence/official-button-build.txt |
| 隔离真实Chromium回归 | 14组通过，包含多等级、跨类组合、编辑失败保留和版本冲突；evidence/official-button-isolated-results.json及official-button-browser-regression.txt |
| 官网按钮全库组件检查 | 两账号各1283真实列表投影、维护/只读两分支；87启用/1196禁用；evidence/official-button-all-companies.json |
| 保存前原文核对 | 484条采纳事实摘录均匹配实际保存原文；281项独立原文审查，19项最终拒绝/暂缓；evidence/enrichment-evidence-check.json |
| 数据保存与保护 | 114条成功，版本保护、在线备份、原始行/来源保留；evidence/enrichment-integration-results.json及enrichment-data-preservation.json |
| 真实两账号API | 各14页全量1283列表、各114更新详情逐字段比对通过；evidence/enrichment-live-results.json |
| 真实页面 | 4家公司×两身份×1440/1920共16组布局；两次新增官网实际网络新标签通过；来源、人员和返回恢复通过，无pageerror；同上 |

本轮未改后端代码，未重新运行此前27项后端测试；前一轮通过记录在coverage/refinement后端证据中。全套前端此前84/85，任务外product-saved-draft断言失败继续保持失败状态；本轮未重跑全套，不宣称全套通过。T-17全站其他业务人工回归仍未执行。

保存前检测到3080/8080/8100均停止，复用既有启动器的进程归属/去重函数恢复核心服务；三端健康及真实登录验证通过。未变更其他worker或授权。

## 页面证据

私人目录：`C:/Users/BJRunner/.agent-reach/baichuan-20261016/enrichment-live-evidence/`，包含20组检查的results.json、16张详情截图、两张官网新标签截图、两张公开人员截图。

- [产品工作台领铄详情1920](C:/Users/BJRunner/.agent-reach/baichuan-20261016/enrichment-live-evidence/product_user-BC0226-1920.png)
- [产品工作台广林详情1440](C:/Users/BJRunner/.agent-reach/baichuan-20261016/enrichment-live-evidence/product_user-BC0136-1440.png)
- [新增官网实际新标签](C:/Users/BJRunner/.agent-reach/baichuan-20261016/enrichment-live-evidence/product_user-official-popup.png)
- [新增公开人员](C:/Users/BJRunner/.agent-reach/baichuan-20261016/enrichment-live-evidence/product_user-new-public-people.png)

主代理已查看最终截图。真实浏览器仅为上述样本，不能将1283条组件SSR检查称为1283家浏览器访问，也未逐家检测全部官网可用性。

## 剩余事项与依赖

| 实际资料覆盖 | 已录入企业 | 剩余缺项企业 |
| --- | ---: | ---: |
| 官网 | 87 | 1196 |
| 电话 | 1026 | 257 |
| 公开人员 | 91 | 1192 |

邮箱46家、地址58家。电话指标为真实库非空字段，不是首轮检索候选数量；未拨测。全部企业已在页面中查询展示，真实源表初始化已完成；尚未达到所有字段信息齐全。缺项需企业公开的一手资料或企业提供资料；不猜域名、不把集团/园区/商业介绍页冒官网，不造人员或资质。万邦仍无确认官网，保持空值/禁用。

未执行：所有电话拨测、全部现任/证书有效性核验、其他部署、全站无关业务人工回归、自动联网定时刷新。没有把这些记为通过。

私人备份/完整预检/来源和逐条回执：`C:/Users/BJRunner/.agent-reach/baichuan-20261016/enrichment-integration/`。其中portal-before.sqlite3为保存前在线备份，remaining-source-gaps.json为逐家缺项表；三个enrichment-all目录保存原文及检索记录，enrichment-audit保存独立审查。

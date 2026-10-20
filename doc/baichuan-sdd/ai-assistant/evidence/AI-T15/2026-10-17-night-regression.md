# AI-T15 / AI-T16 夜间回归与来源边界

所属本地工作区 HEAD ef1676cd8327d693dab897c45a234ba91413884e 加未提交实现。2026-10-17，Windows、Python 3.13.16、SQLite 3.53.1、openpyxl 3.1.5。前端163文件冻结；未修改、构建或重启前端。此记录按实际运行追加，不以准备完成代替验收。

## 来源边界修复

`baichuan_reviewed_enrichment.py` 新增显式 publication_kind，区分 corporate、government、industry、directory、encyclopedia、group、unknown。公开全称只证明此网页声明对应主体，不能升级成工商身份或发证机构核验。新证据 publication_status 为 reviewed_public_publication，legal_identity_verified=false；非官网来源不能补官网。旧冻结批次可读取，已有幂等记录可零写重放；缺少显式corporate的新官网写入被拒绝。旧证据不重写。

`baichuan_facts.py` 要求字段字面声明与实际字段一致；损坏的 field_assertions、identity_basis、identity_method 不能崩溃或以字符串包含/字典键错误认定核实。official_site_basis、publication_kind 的畸形类型由维护工具明确拒绝。复用一份证据不意味着可核实未声明的新字段。公开普通联系字段与证书核验分离。

最终定向检查：reviewed_enrichment、facts、matching 三模块 **47 tests / 23.636s / OK / 无跳过**。命令为 `scripts/baichuan/check_backend.py portal.tests.test_baichuan_reviewed_enrichment portal.tests.test_baichuan_facts portal.tests.test_baichuan_matching`，使用私有Python运行。日志 `.runtime/baichuan-ai-local/night-acceptance-20261017/final-source-facts-matching.log`。

## 合并检查

首次全21模块检查266项未通过，30个异常均为隔离运行器缺少 model_gateway 父目录。未记作产品通过；原失败日志 combined-backend.log 保留。运行器现按服务启动方式加入 backend 及其父目录，仍仅允许显式百川模块、临时文件SQLite与独立存储，清除部署PORTAL环境。

修复后实际 **268 tests / 162.822s / OK / 无跳过**，日志 combined-backend-r2.log；补齐最终边界用例后，全21模块最终实际 **271 tests / 160.018s / OK / 无跳过**，日志 combined-backend-final.log。最终47项包含在此合并运行中，各组有重叠不能相加。维护工具22项检查0.643秒通过，日志 maintenance-tests.log。

持久模型恢复85项和确定匹配36项的独立证据分别见 [恢复修复](2026-10-17-model-budget-recovery.md)、[规则与匹配](../AI-T07/2026-10-17-deterministic-boundaries.md)。真实模型尚待后端加载后另行验收。

## 现有页面只读检查

真实Edge，product和general_manager两角色，各1440、1920、390像素，合计6上下文全部通过：默认收起、覆盖面板不挤窄列表、单一文字/文件输入、可见区域、焦点/Escape、刷新后收起、reduced-motion。没有页面异常或外部请求。6张截图与收据位于私有 night-acceptance-20261017/ui；主执行者已查看390像素截图。

前后163个前端指纹相同；企业1283、模型日志7、任务24、证据1611、修订3349均相同。仅既有账号认证与只读页面操作，0新查询、附件、事实、模型调用。此检查不代替文字/文件真实理解、关闭后台任务或持久对话恢复的验收。

## 容量链路

实际合成1000/5000企业的持久查询、worker、固定快照、XLSX生成、授权下载及openpyxl内容核对通过。每规模一次连接冷样本、三次热样本。首轮因脚本仍期望AI-D19之前partial终态失败；修正为completed、research_policy=independent_manifest_only、research_status=not_requested、研究来源与模型预算0，重跑通过，保留原失败日志及收据。

最终 task-export-capacity-r2.json complete=true：5000家热三样本端到端P95 6038.978ms，XLSX生成P95 3305.407ms，首次快照P95 1350.362ms。P95为有限三热样本nearest-rank，不代表总体保证。两规模确认/候选各半，真实校对全部导出行。无真实模型、联网或实际企业库访问，不以此替代慢网、OCR或真实企业核实。完整私有日志和JSON位于上述night-acceptance目录。

## 继续入口

完成最终合并检查后，仅重载所属portal/worker；保留前端及网关进程身份。随后真实两角色文字、追问、合成公开DOCX、四份XLSX、越权读取及原资料保护另存验收收据。独立资料补录与用户查询分离；未完成全库字段及发证机构核验不升级为完成。

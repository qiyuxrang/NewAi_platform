# AI-T14/15/17：证号链路最终回归及本地后端实际加载

最终25个显式百川模块335 tests PASS191.082s、0跳过，system check无问题。52份核心/测试/runner输入执行前后SHA一致；新14项测试包含6证号+1API投影+7权限，不能把58/70/7专项与335重复相加。首轮中间327 PASS及两次fixture失败均独立保留，不移除旧失败。

新结果快照冻结相关证书编号、主体/类别/等级/日期/核实状态，XLSX逐项依据保留原10列并追加17列。实际ORM→snapshot→XLSX读回001239、公式样式编号均为文本；未知/制造商仍候选，改当前证书后原快照与旧file不变。旧快照缺元数据留白。API逐行副本剔除certificate_records，既有键值/DB快照/XLSX保持，无页面变更。

335项包括严格条件/主体/时点、人工值保护/CAS/回撤、导出与新13路由权限矩阵；由root逐句审阅后，仅AI-AC05/06/07/10/12/14按隔离算法/事实/文件/已实现API范围放行。不是1460条真实资质核验，也不替代未执行的浏览器场景、全库最终数据及远程部署。依据细节见[逐句核账](2026-10-18-025937-acceptance-clause-candidates.md)、[证号专项](../AI-T14/2026-10-18-030744-frozen-certificate-numbers.md)、[接口投影](2026-10-18-031456-certificate-api-projection.md)、[动态权限矩阵](2026-10-18-032136-api-permission-matrix.md)。

实际加载于2026-10-18T03:26:06.803296+08:00，仅portal/worker，新PID28140/17984；前端21632、gateway23540、model-gateway16912身份保持，163前端SHA全部相等。4本地health HTTP200、5服务所属；prepared=loaded当前28源码SHA，仅matching/exports/assistant_api三文件相对上一加载变更。远程与试运行库未修改。

加载前新在线backup quick_check=ok，SHA `8605f7484e072143c72074096d822409a11e5dddeb0027029db3a7e1723427c4`。加载前后13张关键表全部摘要、1283公司/1460原资质/24快照/已有导出与角色密码保持，Model25→25，无active任务；0模型/seed/migration/前端构建重启。原始名录SHA220ec53e…与试运行两文件SHA均保持。旧final-restart收据独立复制并自动归档，未覆盖历史证据。

私有`night-acceptance-20261018/certificate-final-regression/receipt.json` SHA `a4740eb1b7da5e062926f7de7e2396489d9c535113544b273f72ef5fa8553b23`；full.log SHA `0e931a965df34ad300c1cee7c3dc215c486e1902ad4facdaf3801237fe000130`。`certificate-owned-backend-load/receipt.json` SHA `81d129967eb7528b0cc6df42f03b35fbb2280230052387daec7a6b8ba9513877`；其中含before/after、真实health、28文件SHA、唯一重启收据及旧收据SHA。新实际1283只读匹配[另测](../AI-T16/2026-10-18-certificate-metadata-actual1283-readonly.md)，不是加载health推算性能。

功能AI-T14恢复DONE；AI-T15/17整体继续。数据当前70批248家536原空字段，原1460资质独立核实0、官网101/1283、电话1032/1283；全库未完成。独立70批一致性阶段审计使用冻结副本，后续增量分开。

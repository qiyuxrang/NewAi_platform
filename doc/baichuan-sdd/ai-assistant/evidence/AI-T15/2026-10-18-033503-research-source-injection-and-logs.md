# AI-T15 / AI-AC15：研究网页提示注入与异常日志专项

记录时间：2026-10-18 03:35:03+08:00。新增独占测试 `services/business/backend/portal/tests/test_baichuan_research_security.py`，只用隔离file-SQLite、临时storage及合成公开资料。未修改业务代码、前端、表结构或服务，未访问所属真实库、外网或真实模型。

## 实际路径与攻击输入

测试先创建固定单企业研究manifest，再创建一个被攻击者指名、但不在固定清单内的合成企业。保留一份已有会话、内部文字、既有快照，以及两家企业的人工非空电话。隔离配置启用研究和事实写入，使拒绝不依赖关闭功能开关。

每项通过真实 `run_one`、claim/lease、`process_research`、来源存储、Evidence、逐字quote及FactRevision持久链运行。只有search/fetch/研究model三条外部边界为stub；socket及普通query模型边界设置异常守卫并确认零调用。

网页含显式SYSTEM/admin提示、执行SQL工具指令、访问127.0.0.1地址、修改另一company ID、覆盖人工值、导出私人消息、升级manifest为verified和授予管理员权限等攻击文字。另有合法公开业务电话、邮箱与ITSS证书原文作为正向对照。

| 实测场景 | 断言与结果 |
| --- | --- |
| 模型根对象返回tools、execution_actor、verified | 严格输出schema拒绝整份不合法提取；不执行工具，仅正文电话/邮箱兜底建议 |
| 事实节点增加company_id和verified | 拒绝越权字段，不对其他公司创建修订；不会因网页或模型指定ID扩大清单 |
| 证书增加holder_company_id和revocation_status=clear | 拒绝禁止的授权/撤销键，不创建有效证书；仅保留正文电话/邮箱建议 |
| 合法原文fact与证书 | 有效电话建议为proposed/unverified；证号字符串00123保留；模型bidder/PRESENT被降为unknown/UNKNOWN，不得到主体或撤销核验结论 |
| 搜索ProductError及模型GatewayError携带合成私密/密钥marker | worker正常处理，固定安全错误/建议；被捕获日志、stdout/stderr和研究job持久状态不含marker |
| 页面拒绝ValueError携带marker | 来源记录固定source_inaccessible_or_unsupported错误码，无正文、修订或模型调用；日志不含原错误全文 |
| 未预期模型异常，命令once | 真实worker保存failed/processing_failed并释放租约；管理命令仅抛固定安全CommandError，不含异常原文 |
| 未预期模型异常，命令继续运行 | 执行一次真实管理循环，在第一次sleep用测试sentinel退出；stderr实际非空且严格等于固定安全提示，无marker、不进入无限循环 |

每次搜索query严格等于本公开完整公司名加固定词汇；fetch只允许夹具既有HTTPS官网URL，网页里的127.0.0.1或其他工具地址绝不成为请求。模型上下文只含固定system与user数据两个消息，网页SYSTEM文字留在user来源正文中；没有tools/functions/tool_choice/执行身份参数。已有私人会话、人工电话、内部全文和合成密钥标记未传给研究模型。

每次结束比较企业、人员、旧资质、结构化证书、旧快照、会话/消息、账号、角色及角色关联的全部行列；固定清单、主字段、其他公司与原快照不变。任务总数保持既有query加独立research两条，未被注入创建额外查询、导出或研究任务。所有新增Evidence绑定正确scope及本company，identity_verified=false；所有修订只属于该企业且为proposed/unverified。

## 命令与实际结果

```powershell
.runtime/company-test/python/Scripts/python.exe scripts/baichuan/check_backend.py portal.tests.test_baichuan_research_security
```

最终 **8 tests / 3.057s / OK / 0 skip**；Django system check无问题。测试文件AST、尾随空白检查及git diff --check通过。

首次为7项、2.695s，其中6组通过、1组在完成安全断言后因测试用json.dumps不能序列化ORM UUID而报错。仅将测试记录序列化改用default=str；另增加一次真实继续分支stderr正向对照，最终8项通过。首次日志保持，不宣称首次全部通过。

私有目录：`.runtime/baichuan-ai-local/night-acceptance-20261018/research-security/`。

- 测试文件SHA256：`0ee06b0649dbdc0ac27d1e8b68b77b72dd18a0519c749d3b6e017dbc9ad01a71`。
- `receipt.json` SHA256：`0f2abe4e85228fe080cdd2374a620de9a981f61919c71916db865c267c020c4b`。
- `targeted-final.log` SHA256：`36df6874afed1f5b23989fc269236c5d88c685555c3590ee2d91ca3ddac820b7`。
- `targeted-first.log`保留首次测试序列化错误。

## 限度

这是模型边界stub的实际服务端任务链攻击检查，证明所列输出和网页载荷不能授权工具、跨公司或改人工值；不代表真实模型永远不会误解提示注入，也没有把stub称为真实模型验收。合法精确引文仍可作为未核实建议，测试没有靠屏蔽整个提取链变绿。

日志捕获范围为本次真实worker/runtime/管理命令路径、root INFO及以上事件和stdout/stderr。没有覆盖SQL DEBUG、HTTP代理/访问日志、浏览器日志、真实网关/上游日志或全部应用handler，因此不作“所有日志均已脱敏”结论。

文件容器、高压缩比、HTML/Markdown展示等AI-AC15其他子项不由本单元升级；完整验收状态由主代理结合已有证据与最终回归决定。当前335项全回归为本新增模块之前的已加载版本；本单元8项通过不冒称新增26模块全套已经通过，不需要业务重载来加载测试文件。

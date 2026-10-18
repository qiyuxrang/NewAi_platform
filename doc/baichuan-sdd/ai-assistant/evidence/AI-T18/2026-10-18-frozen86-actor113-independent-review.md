# AI-T18：86批613字段冻结样本的actor113独立复核

本次只复核已冻结的86维护批、613字段样本；主线程后续实库已推进至87批614字段，本单元没有读取实库，也不把旧样本称为当前全库验收。

原v2核账对113项updated_by变更只检查同actor最近允许类型revision和旧更新时间下界。本独立补充没有修改该v2脚本、回执或档案，进一步核对113项均对应该企业全部revision范围中的实际最新revision，并绑定已批准来源集合及真实事务顺序：

- 112项certificate_observation：revision/evidence/certificate属于原162公开观察批准集合，三类共486整行SHA均独立复核，相关112个audit整行SHA也符合原批准集合。baseline_version精确对应当前版本减一；时间为旧company时间 ≤ certificate revision ≤ 当前company时间 ≤ 对应audit。实际revision到company更新时间差5.752至10.537毫秒。
- 1项reviewed_enrichment_batch：精确属于冻结86批集合，UUID stamp、item digest、应用字段revision、来源subject、actor、current version及对应audit一致。按实际源码事务顺序，字段revision ≤ company更新时间 ≤ batch stamp ≤ audit；实际stamp比company时间晚3.984毫秒。

上述毫秒数是实际观察，不是新造的时间容差或性能阈值。不能统一要求最新revision早于company更新时间：公开证书revision在CAS前创建，维护batch stamp在最后字段CAS之后创建。

实际重哈希257项冻结输入及两个冻结SQLite样本；613字段链仅独立重数为613个不重复企业字段、282家，没有重跑原613条完整SQL关联验算。当前原coverage已经正常推进，复核只使用其86批冻结副本；该差异明确记录。另独立重哈希6份新增批次backup，与冻结state及v2回执一致；原80份backup继续沿用既有阶段证明，本次未重新hash。

只建立2个明确批准的冻结SQLite只读连接，启用query_only及写操作authorizer拒绝；实库SQL、SQL写入、网络、模型、业务写入、源码、前端、服务和共享状态文档修改均0。两个审阅路径错误及一次rg通配符用法错误明确保留在独立回执说明；实际actor检查脚本首次执行通过。

这证明冻结样本的批准修订链与元数据一致性，不重建历史权限/登录变化，不证明样本之外没有操作，也不独立核实来源新鲜度、法律主体、电话可接通或发证有效性。原v2首版失败记录保持，正式AI-T18最终审计仍未开始，全库未完成。

私有证据目录：`.runtime/baichuan-ai-local/independent-enrichment-20261017/actor113-independent-review-20261018-0625/`。

- `receipt.json`：SHA256 `65f8d3e9dbdd6e361229d0fe5c37f07000a45af2a3bbc43da39ad282db19027d`。
- `actor113-tightened-details.json`：SHA256 `78fce4dbe9332ad12a1d662dc6dc72f52cb53c3c054e8d270196412471e9d8bd`。
- `frozen257-checks.json`：SHA256 `d707dc30c7d8c250cbcc68df14ac9628df9ac421e17e0c11652b1ab0dbb1b245`。
- `new6-backups-independent-recheck.json`：SHA256 `eb3a71202e5eb096238917b0ac9fbffd38d76d9e4bef9304c366f964204f6197`。
- `complete-input-manifest.json`：SHA256 `ca6ee930aee10ae9db296c8037f3b89a53e0e3ac6c7f00d6ba9dca665bf7f8a1`。

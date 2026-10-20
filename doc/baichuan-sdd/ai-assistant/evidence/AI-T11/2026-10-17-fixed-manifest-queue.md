# AI-T11 固定清单与研究进度底座

日期：2026-10-17（北京时间），工作区基线 `ef1676cd8327d693dab897c45a234ba91413884e`。环境、解释器和隔离 SQLite 配置沿用 AI-T03，测试实际使用 Django 内存库；样本明确为虚构企业。没有把空本地库或历史数量当作真实在库数量。

实现：`baichuan_research.py`、`test_baichuan_research.py`，助手 API 增加维护者创建/查询清单入口。新增数据源确认配置默认关闭；实际数据源研究还须具有目标确认标记和备份引用，隔离样本须有 isolation 标签。

执行：

```text
manage.py test portal.tests.test_baichuan_research --verbosity 2
manage.py test portal.tests.test_baichuan_research --verbosity 1
```

首轮6 tests / 5.450s / OK；增加失败重试后7 tests / 8.698s / OK；system check 0 issues。

与任务模块新增 request_hash 保护联调时，发现创建清单后追加 manifest_id 会破坏原请求哈希；已改为按 scope/owner/幂等键确定清单 UUID5，并在初始 enqueue payload 固定，后续不改任务请求。修复后和模型/事实/研究运行器联合 38 tests / 29.064s / OK，详见 AI-T10 证据。

实际验证：

- 固定清单保存全部当次 ID、企业版本和 12 类研究字段；每公司/字段建研究工作项和任务工作项。后续新增企业不会改变旧清单分母；重复请求不重复建队列，内容不同的同幂等键拒绝。
- 新增企业进入独立增量清单，排除整条祖先链已包含 ID；禁止跨源增量。没有增量时状态明确 empty，coverage 为 null，任务 partial，不能报 100% 完成。
- 创建要求维护权限；报告按维护者所有权及部署隔离。只读身份、他人清单和跨部署引用实际拒绝；未确认数据源/无备份的真实标记实际拒绝。
- 有效租约和 fence 下，每批最多 200 字段，研究项、任务项、真实统计和恢复点一起提交；同一已完成结果幂等，改变结果拒绝。批内后一项无效时前项也回滚；过期执行者被拒绝，新执行者从已保存项继续。
- failed 可由关联重试任务继续，复用原清单分母；保留旧任务工作项结果和 previous_attempts，已完成字段不重复研究。
- 统计分别给出已研究企业、全部字段核实企业、核实字段数量和各字段 verified/not_found/not_disclosed/inaccessible/conflict/pending_review/failed 等计数。not_found/inaccessible 不改公司电话、人工值，也不写 ABSENT。
- 固定清单引用保护企业，删除不会静默缩小分母；合并/删除情况可记为明确研究状态和原因。

本证据覆盖队列与统计、恢复，不代表真实清单已创建或全库已研究。真实外网的小批次核查、目标库源确认和备份、逐企业完整研究与最终核账仍在 AI-T10/AI-T12/AI-T18 验收。

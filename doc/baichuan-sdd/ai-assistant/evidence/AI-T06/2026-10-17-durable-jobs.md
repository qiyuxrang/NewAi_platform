# AI-T06 百川持久任务底座隔离验证

日期：2026-10-17（北京时间）；基线 HEAD `ef1676cd8327d693dab897c45a234ba91413884e`，含当前未提交增量实现。变更：`portal/baichuan_jobs.py`、`portal/tests/test_baichuan_jobs.py`；依赖新增模型及 0046 迁移，不修改真实数据。

复查命令（根目录）：

```powershell
& .runtime/company-test/python/Scripts/python.exe doc/baichuan-sdd/ai-assistant/evidence/AI-T02/probe_capabilities.py --jobs-tests
```

解释器 Python 3.13.16、Django 5.2.18；探针清除部署环境变量，创建并销毁 `.runtime/baichuan-AI-T02-*/test.sqlite3`，仅虚构用户和工作项。数据库迁移 0001—0046 实际成功。最新结果：**14 tests / 14.067s / OK**；Django system check 无问题；`git diff --check` 通过。没有外部模型/搜索请求或真实库写入。

已验证：

- 任务按所有者和部署 scope 隔离，他人/不存在/跨部署均 404；外人会话和替换执行身份被拒绝。
- 幂等键按用户/scope 唯一，相同内容只建一次，同键不同内容 409；JSON、大小、类型、预算及布尔伪整数有界拒绝。
- 只读可查询/导出，研究任务需要维护权限；每次领取、心跳、保存、工作项发布重查当前用户和执行身份授权。
- 实际模拟进程丢失（持久 checkpoint 后租约过期），新 worker 接管并增加 fence，保留进度/部分结果；旧 fence 和过期租约的 heartbeat、save_job、save_item 全被拒绝。
- queued/running/awaiting_input 取消均立即进入 cancelled，fence 增加，未完成工作项取消，迟到结果不能落库；重复取消保持终态。
- awaiting_input 释放工作租约，不占线程等待；显式 retry 创建新 job，关联 parent，复制恢复点及部分结果，原尝试不改写，重试同键幂等。
- 模型/来源预算在调用前原子预留；达到上限后拒绝更多用量，不允许通过普通进度计数重置；有结果保留 partial，无结果 failed；时长和回收尝试次数有上限。
- 权限撤销在拒绝写入时同时持久 failed/permission_revoked、清租约；未发表的 checkpoint 不落库。
- 完成工作项不重复覆盖；`leased_job` 提供事实修订与工作项/检查点的同一短事务，模拟提交前崩溃时全部回滚。
- 两个真实线程同时提交和领取，只创建一个工作、只一个领取成功。
- **两个独立 OS Python 进程**在同一 SQLite 测试库同时提交、再同时领取；验证进程间（非仅 RLock）幂等与排他领取，最终 attempts=1/fence=1。子进程只继承白名单环境且结束，未启动常驻 worker。

公共契约见模块函数：enqueue_job 返回 `(job, created)`；claim_job 返回 claimed job 或 None；job_for 私有读取；heartbeat/save_job/save_item/consume_budget 必须带 `job_id/worker_id/fence`；cancel_job/retry_job 要求用户；leased_job 仅包裹短数据库提交，禁止在事务内联网或模型调用。

AI-T14 集成后补充：retry_job 对原始完整请求重新计算 hash，拒绝提交后被改写的请求；export 重试另建与原固定快照关联的 BaichuanExport，不复制旧文件。HTTP retry → 实际 run_one → 新 XLSX 下载已真实通过。最终合跑命令 `probe_capabilities.py --job-export-tests`：**任务 15 项 + 导出 15 项，共 30 tests / 25.183s / OK**；包含上述新增完整性测试，系统检查无问题。

默认预算为 timeout_seconds=120/max_model_calls=8/max_sources=12/max_attempts=3，均可在硬上限内配置。租约 1—300 秒，默认 30 秒；长模型或 OCR 阶段需更长租约或定期心跳。counts 不生成虚假百分比。feature flag、HTTP 会话、实际 worker 编排、刷新 UI、真实部署和千家/五千家锁竞争性能由后续集成/性能验收继续覆盖；不将 AI-AC13/14/17 整项冒充 PASS。

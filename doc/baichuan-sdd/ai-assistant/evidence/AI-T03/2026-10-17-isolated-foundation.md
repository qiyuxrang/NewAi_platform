# AI-T03 隔离模型与增量迁移单元

- 日期：2026-10-17（北京时间）；基线 HEAD `ef1676cd8327d693dab897c45a234ba91413884e`，工作区新增实现，尚未提交。
- 环境：Windows、`.runtime/company-test/python/Scripts/python.exe`、Django 5.2.18。显式启用调试、关闭 HTTPS（仅隔离测试）、设置测试专用 secret；移除继承的 `PORTAL_DB*` 环境。配置 SQLite 指向 `.runtime/baichuan-ai/models.sqlite3`，Django 测试实际创建 `file:memorydb_default?mode=memory&cache=shared`；没有连接目标库或远程服务。
- 范围：`portal/baichuan_assistant_models.py`，`portal/models.py` 导入，`0046_baichuan_assistant_foundation.py`，`test_baichuan_assistant_models.py`。

## 实际执行

在 `services/business/backend` 以以上解释器执行：

```text
manage.py makemigrations portal --name baichuan_assistant_foundation
manage.py test portal.tests.test_baichuan_assistant_models --verbosity 2
manage.py makemigrations --check --dry-run
git diff --check
```

结果：7 tests / 16.012s / OK；system check 0 issues；No changes detected；diff check 无错误。

## 覆盖与观察

1. 13 个新增模型覆盖证据、追加事实修订、通用多证、版本规则、所有者会话/消息/附件、持久任务/工作项、不可变匹配快照、固定研究清单/字段工作项与导出。
2. 迁移仅新增表、索引/约束及新表间外键，不修改已有 Company、CompanyQualification、CompanyPerson。测试从 0045 保存虚构企业/资质/人员全字段（含 ID、人工电话、官网、Excel/官网来源、版本），迁到 0046 后逐字段对照相等，新增证书/修订表为空。对尚无新事实的隔离库反迁 0045，再次对照旧字段相等，最后恢复 0046。
3. 旧资质转换为显式维护函数，维护权限与当前企业版本必须通过，重复执行不重复记录；原 PRESENT 仅映射为未核实声明，保留旧 ID、来源、旧 verified_on 原值但不升级核验状态。原企业、人员、资质全部值保持不变。
4. 删除旧资质子项后映射证书和来源修订仍可追溯；证书/历史持有 Company 的 PROTECT 引用。旧子项仅记录 UUID，不让旧快照编辑级联删除新证据。
5. 证据/修订/快照阻止实例修改、QuerySet update/delete 及以现有 UUID 构建实例覆盖；证书日期区间、任务合法状态、会话消息幂等、任务幂等、工作项/快照修订唯一约束均有实际负例测试。

## 边界与恢复

- 这是 AI-T03 的隔离实现证据；目标数据源未据此确认，未执行目标迁移、回填、全库研究或部署。旧 API 双读与旧编辑接入在 AI-T05/AI-T07 继续验收。
- 反迁仅演练**新增表为空**的情形。有新证据后不能靠删除新增表回退；应关闭入口和写入、保留表与修订，在统一服务中按版本回撤本批事实。
- 所有权字段与外键只提供持久结构；跨用户/跨部署访问须在服务/API 每次重新校验，不能把本单元当权限接口验收。
- 下一步：AI-T05 统一事实建议/证据验证/冲突保护与旧编辑修订接入；AI-T06 复用已冻结模型实现任务租约与 fence。

# AI-T05 事实建议、人工保护与修订单元

日期：2026-10-17（北京时间）。代码基线 `ef1676cd8327d693dab897c45a234ba91413884e`，新增未提交实现。环境与隔离数据库配置见 AI-T03 证据；没有访问目标库。

## 实际检查

在 `services/business/backend` 使用 `.runtime/company-test/python/Scripts/python.exe`，显式隔离 SQLite、调试开关和测试 secret，移除 `PORTAL_DB*`：

```text
manage.py test portal.tests.test_baichuan_facts portal.tests.test_baichuan --verbosity 1
```

25 tests / 36.696s / OK，1 项既有 PostgreSQL 专用检查在 SQLite 跳过；system check 无问题。之后补充事实开关、写入前刷新执行身份与错误规范化，再针对受影响单元执行：

```text
manage.py test portal.tests.test_baichuan_facts --verbosity 1
```

10 tests / 6.813s / OK；system check 无问题。

## 已验证行为

- 统一字段服务仅在维护权限、当前企业版本、有效证据和 `BAICHUAN_FACT_WRITE_ENABLED=True` 同时满足时补空。旧人工非空值不同进入 conflict；只读身份和写入开关关闭均仅保留 proposed 建议。
- 正文、定位、64 位内容哈希、核验日期、企业主体身份与部署 scope 缺失/不符，不变成已核实事实。搜索摘要不算正文证据。
- 通用证书要求原始颁发/主管机构或可验证证书，投标人主体、范围与完整日期；明确“clear”撤销状态必须有同次核验记录。制造商、未知日期、未核对撤销和 ABSENT 声明不会被写为可靠企业资质。
- 合格证书只追加精确类别/等级的七类兼容投影，保存投影→证书→来源修订关系；不删除旧等级和证号。矛盾旧人工证书保留并进入冲突。
- 旧 `save_company` 在原有锁和事务内追加人工字段/子项修订，包含被删除子项的旧来源。原资质被修改或删除时对应旧映射标 superseded，证据、旧值和来源修订保留；人工编辑不自动升级为 verified。
- 公司版本冲突拒绝写入；撤销维护身份后不能继续写。字段回撤追加修订，只有企业版本及字段值仍对应本次应用时才恢复该字段，后续人工改动受到保护。
- 原百川的列表、精确筛选、详情、旧编辑、权限与版本化回归在本轮实际运行。

## 边界与下一步

此处是本地服务与兼容编辑的验收单元，不代表目标库迁移、真实外网证书核验或全库研究完成。证据 acquisition/身份判断需要研究适配器实际执行；此模块不会凭空生成网页核实状态。全库字段队列与覆盖报告在 AI-T11 继续，API 的跨用户对象隔离和完整链路由 AI-T15 另验。

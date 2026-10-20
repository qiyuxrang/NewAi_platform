# AI-T05/12：公开 ITSS 证书观察的专属维护入口

2026-10-18 04:37:50 +08:00。本单元代码与隔离专项已完成，**尚未加载服务、尚未执行主库补录**。依据本轮已更新的 AI-D24 和 04:28 冲突细化实现；原 1460 条声明、历史快照和人工事实不投影、不覆盖。

## 实际实现

- `services/business/backend/portal/baichuan_facts.py` 新增 `validate_public_certificate_observation`、稳定全字段身份函数及 `record_public_certificate_observation`，保留原 `propose_certificate` 行为。
- `scripts/baichuan/apply_public_certificate_observations.py` 是独立离线维护 CLI，默认 inert。执行必须显式提供批次路径及完整 SHA，检查本任务所属本地源表库、原件哈希、1283 ID 集合、当前主体与版本；取得既有维护锁后整批预检、在线备份、逐项原子提交及私有恢复检查点。
- 只有有维护权限、来源 scope 一致且本进程两个显式开关同时开启时才能新增。部署未定义的新 publication 开关默认为 false；CLI 仅对专属维护进程临时 override，不新增 API 或自动任务。
- 原始采集 raw 必须按 UTF-8 解码后等于保存正文；原正文、HTTP 200 收据、公共 IP、正常 TLS、同目录原文件名、URL、采集时间、SHA、全文定位和逐字段断言全部绑定。正文 JSON 必须与精确主体的原始公开记录一致，搜索摘要不可替代。
- 新增独立 Certificate、Evidence、FactRevision，不修改原 legacy/projection。`startDate`、`getDate` 保留原标签于正文和修订，绝不转为有效起始日期；issuer、standard、scope、valid_from 和撤销状态继续未知，评估机构不是 issuer。
- 正常观察 Certificate 为 unverified；同号双方已知字段矛盾或同一公开记录明确字面变化时，新观察为 conflict、verified_at 仍为空，Revision 始终 unverified 并记 public_conflict。原 verified 记录不改；新未知不否认旧已知，不按类别/等级同义写法制造冲突。
- 全字段稳定指纹与 UUID 支持精确重放；重放还检查证书、来源和修订的内容及关联，篡改立即拒绝。旧版本的已完成相同批次可以安全重放，不重复增加版本或记录。

## 实际检查

在独立临时文件 SQLite、隔离存储中执行：

```powershell
.runtime/company-test/python/Scripts/python.exe scripts/baichuan/check_backend.py portal.tests.test_baichuan_public_certificate_observations
```

最终 **21 项 / 10.287 秒 / PASS / 0 skip**，覆盖两个默认关闭开关、只读/失活/改密权限、严格整数 CAS 和外 scope 拒绝、三级/二级/通用要求三种真实结构、原声明与人工记录保护、正常及冲突观察精确重放零增量、全文来源拒绝、事务失败与权限撤销回滚、关联篡改拒绝、旧快照不变及匹配保持 candidate。旧有效 verified 同号遇明确相反公开到期日后实际为 conflict/candidate；新缺项但已知字段一致时不制造冲突。

测试网络入口被拒绝；测试 SQL 仅限新建的临时隔离库。另对根准备的 **Q4–Q10 七批、162 条真实记录**执行纯 validator/provenance 预检：PASS，实际阶段 **0 SQL / 0 HTTP / 0 model / 0 主库写入**；SQL、DNS、socket create、socket connect 四个拒绝自检均实际触发并被阻止。Django 仅 setup，不连接业务库。这项检查不代替实际执行时的最新版本、权限及 CAS 预检。

失败记录保留：首轮 20 项有 1 项规则夹具漏 source，返回 unknown；修正为完整有效规则后 20 项全过。补充关联篡改用例的首轮被既有 append-only ORM manager 拒绝，随后仅在隔离测试库使用原始 SQL 模拟损坏，21 项最终全过。早期离线准备器的缺失字段/Path 比较失败同样保留，未据其声明通过。

## 冻结与恢复

| 文件 | SHA256 |
| --- | --- |
| baichuan_facts.py | `19efbed913a75a76e813b1991537854a16664f9d25ee108c8bcdc30c522d930c` |
| test_baichuan_public_certificate_observations.py | `027425a8f187a9d3e7a757205adad1ed696c3261ea1082930b6cd527e0370984` |
| apply_public_certificate_observations.py | `040cb88ad7f2d2533fd2d20e22d0956ba34b28a4ae5912d04aec0444f19ad6da` |

私有证据根：`.runtime/baichuan-ai-local/independent-enrichment-20261017/qualification-publication-sandbox/`。

- `observation-targeted-first.log`、`observation-targeted-after-fix.log`、`observation-targeted-final.log` 和 `observation-targeted-final-corrected.log` 保留测试全过程。
- `actual-162-offline-preflight-receipt.json` SHA `512e2f7ff839703293625694d1b7ea777d2d0014c97908d218633f7cf05c9cdc`，绑定原七批、162 条来源与当时相同的核心/CLI；其 test SHA 是补充重放用例前版本，最终专项 test SHA 以本表为准。
- `observation-unit-final-receipt.json` 保存本轮最终代码、日志和公开证据哈希。

下一步由根代理统一审阅、最终相关回归、仅后端加载，然后受控小批试用。当前 162 条仍是可追溯公开资料候选，不能记为已补录或已核实证书，不能据此提高 confirmed；全库其他资质渠道仍有独立缺口。本单元无主库、模型、联网、前端或服务操作。

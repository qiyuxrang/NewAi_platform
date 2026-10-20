# AI-T16：实际 1283 企业结构化匹配独立计时

本独立单元弥补既有性能核账的明确缺口：此前实际 1283 企业真实查询未保存 match_companies 的独立分段；合成 1000/5000 基准与模型/文件/浏览器耗时均不能替代这一分段。

## 准备状态

根代理审阅冻结脚本后通知静止窗口，唯一实际执行 PASS；准备默认模式与隔离检查均保留。全库原资料、全部逻辑表与前端指纹保持，没有新模型或业务写入。

私有脚本：.runtime/baichuan-ai-local/night-acceptance-20261018/actual-catalog-match-ro.py。

最终准备 SHA256：`6565244f6c4a549616815960f43c77f465067437d1cc2e9d4aa082547cbfccbf`。

默认模式实际返回 prepared_not_executed，SQL/HTTP/模型 0。test_actual_catalog_match_ro_preparation.py 实际 7 tests / 0.047s / OK / 0 skip（此前准备首轮 7 tests / 0.052s）。纯临时 SQLite 验证 mode=ro 与 query_only 拒绝 UPDATE/DDL，拒绝非 owned 目标；另测 SELECT 门禁、网络拒绝、默认零调用、attempt 防重复、全表摘要与最近秩 P95。

## 实际输入及限制

只读使用已有 GM 纯文字快照 e1098dd0-7111-4846-9694-5a20cdf244aa 的条件及 owner2；直接调用纯 match_companies，不经过 worker、模型、任务或 save_match_snapshot。默认精确电子二级/制造商 CCRC 二级、ITSS 仅优先；预期实际 1283 明细、0 确认/1283 候选/0 排除。

一个专用子进程，1 个连接首样本 + 12 热样本，对热样本计算最近秩 P95，与 2000ms 初始目标对照。计时包含权限重读、条件编译、规则/事实 ORM 读取、确定规则求值和排序；不包含摘要计算、快照写入、模型、HTTP、绘制或 XLSX。没有清理 OS 缓存，不称 OS 冷启动或总体尾延时。

最外层禁 DNS/socket，所有 SQLite 连接仅允许 fixed owned URI mode=ro，连接即设置 query_only；计时区 ORM 只允许单条 SELECT。前后每张 SQLite 表行数与完整内容摘要、模型日志数和 163 前端 SHA 对照；只保存摘要，不复制账户/password/token 原值。输出实际 Python/SQLite/Django/平台版本及匹配、条件源码 SHA。真实业务写入、模型、HTTP、前端改动与服务操作均预期 0；若结果超时或保护失败保留实际 FAIL，不重试掩盖。

## 实际结果（2026-10-18 02:00:55–02:01:03，+08:00）

执行命令：`.runtime/company-test/python/Scripts/python.exe .runtime/baichuan-ai-local/night-acceptance-20261018/actual-catalog-match-ro.py --execute`。

| 分段 / 保护 | 实际 |
| --- | --- |
| 环境 | Windows / Python 3.13.16 / SQLite 3.53.1 / Django 5.2.18 |
| 连接首样本 | 463.688ms |
| 12 个热样本最近秩 P95 | 553.167ms，低于 2000ms 目标 |
| 实际结果 | 每轮 1283 条、0 confirmed / 1283 candidate / 0 excluded |
| 单轮 SQL | 24 SELECT，共 13 轮 312 条；无写操作 |
| 一致性 | 13 轮完整匹配结果摘要相同，原表全部前后摘要一致 |
| 模型 / 网络 / 新快照 | 0 / 0 / 0；模型日志 22→22，既有快照保持 |
| 前端 / 服务 | 163 文件 SHA 保持，0 修改/重启 |

结果摘要 `76aee1ff6e72849ebf0d38beb6300abc66ccdfa3448b38a210c7a6f6f3140af6`。源码 matching SHA `05255c015121ee5fbf021af2cda8ca77b2d55b4102b52729f9a29b6bcfe1b334`，conditions SHA `e85e4fa6a6c725a7bf896e9bd6373a0a5277dfcc90239b4423d0279a8967a361`。

私有 actual-catalog-match-ro/receipt.json 保存全部 13 样本、表级保护摘要和版本，SHA256 `924866756fab217ffbd1e5785d5d90d878310fa960e73c825a74a37cfdf8a75f`。本单元只放行此固定实际库/条件/专用进程的结构化匹配性能，不代替浏览器首屏绘制、真实并发、总体 P95、五千家实库或模型性能；未知证书仍保持未知。没有重跑已有模型/文件/导出场景。

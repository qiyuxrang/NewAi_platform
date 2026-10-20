# AI-T16：千家/五千家隔离链路资源实测

2026-10-18。实际复用未修改的 `scripts/baichuan/benchmark_assistant_e2e.py`，通过独立私有wrapper增加Win32资源读数。全新临时SQLite、完整迁移/seed、合成企业及证据；1000家、5000家各1个连接冷样本和3个热样本，单子进程、单worker串行。硬超时240秒，无重试，实际子进程53.938秒完成；CPU消耗52.672秒，含7.770秒schema setup、夹具、8次链路及监测开销。

条件通过现有任务checkpoint恢复，**排除AI理解**；真实消息入队→worker→固定快照→导出消息→worker→XLSX落盘→授权打开→三表逐行重读均实际执行。每次确认/候选各一半、2N数据行、无公式，8次查询和8次导出全部completed，未把全部未知候选作为性能通过理由。临时库与存储结束后实际删除。

## 隔离与环境

Windows11 10.0.26200、Intel64 Family6 Model140 Stepping2、8逻辑CPU；Python3.13.16、SQLite3.53.1、openpyxl3.1.5。仅本基准并发1，同机未独占，不声称宿主机空闲。清除继承业务环境，临时路径必须在受控 `assistant-e2e-*` 下。额外同时拦截 `sqlite3.connect` 与 `sqlite3.dbapi2.connect`，仅允许该临时 `synthetic.sqlite3`；实际3次连接均同一临时库。socket/DNS及网关调用禁止；实际模型/网络调用0，实际企业库访问、认证、服务和前端改动0。不新增依赖，不修改核心、测试或基准源文件。

冷样本只关闭Django连接，未清OS缓存；5000家在同进程从1000扩充而来，不是重新启动进程的冷样本。热P95采用3样本最近秩，等于最大样本，仅探索性结果，不推断总体尾延迟。

## 分段耗时

单位ms。总链路包含授权打开及openpyxl三表重读；首快照就绪不等于真实浏览器首屏。

| 段 | 1000冷 | 1000热中位/P95 | 5000冷 | 5000热中位/P95 |
| --- | ---: | ---: | ---: | ---: |
| 结构化匹配 | 184.069 | 280.690 / 399.660 | 1061.089 | 1289.149 / 1331.128 |
| 消息至首快照 | 301.952 | 399.676 / 513.302 | 1248.867 | 1471.136 / 1526.034 |
| XLSX构建 | 990.021 | 903.018 / 1047.155 | 5033.884 | 5228.890 / 5430.637 |
| 总链路及重读 | 1788.587 | 1917.362 / 1952.555 | 8446.380 | 8989.682 / 9228.994 |

热样本阶段CPU中位数：1000/5000匹配分别281.250/1265.625ms，匹配连同快照312.500/1375.000ms，XLSX构建906.250/5218.750ms。GetProcessTimes计数有约15.625ms粒度，短发布阶段显示0不表示不消耗CPU；匹配与快照是嵌套阶段，不相加当整体CPU。整体CPU约占一核心等价97.653%，不是8核宿主机总体占用。

本轮千家确定匹配热P95低于2秒、排除AI后的首快照低于5秒，仅对应合成测试范围。5000家完整XLSX链路热P95约9.229秒；规格的5秒首批目标不能套用为完整导出目标，也不能据此宣称真实模型文字首批或浏览器1秒反馈通过。

## 内存与文件资源

GetProcessMemoryInfo读取当前/OS峰值working set、PrivateUsage及峰值commit charge，GetProcessTimes读取user/kernel CPU。目标50ms采样，实际668个读数，中位间隔74.663ms、最大间隔272.734ms；Python调度/GIL影响采样。PrivateBytes峰值是采样下界，**OS peak commit与peak private不混称**。

| 整个子进程读数 | 字节 | MiB |
| --- | ---: | ---: |
| 最终当前working set | 308973568 | 294.660 |
| OS峰值working set | 339554304 | 323.824 |
| 最终当前private bytes | 528388096 | 503.910 |
| 采样峰值private bytes | 552689664 | 527.086 |
| OS峰值commit charge | 559632384 | 533.707 |

私有JSON逐段保存before/after资源读数、CPU和对应临时SQLite字节数。1000家4次消息/快照/导出后SQLite8605696字节，扩充5000家再做4次后40394752字节；包含累计任务/快照，不能视为单次查询或单家公司成本。1000家XLSX245683—245695字节，5000家1183348—1183363字节；最终8份私有产物5716163字节，随后随临时目录清理。

没有预设RSS/private硬上限，本轮资源结论为 **OBSERVED_ONLY**。未验证多worker、同机极端竞争、实际AI/公网/OCR、长期驻留或真实库资源；不能给不存在的内存阈值标PASS。

## 复现与收据

私有目录：`.runtime/baichuan-ai-local/night-acceptance-20261018/synthetic-e2e-resources-20261018/`。实际执行命令：

```powershell
& '.runtime/company-test/python/Scripts/python.exe' -X utf8 '.runtime/baichuan-ai-local/night-acceptance-20261018/synthetic-e2e-resources-20261018/measure.py'
& '.runtime/company-test/python/Scripts/python.exe' -X utf8 '.runtime/baichuan-ai-local/night-acceptance-20261018/synthetic-e2e-resources-20261018/summarize.py'
```

wrapper拒绝覆盖已有intent；后续复验应先复制到全新同层目录，旧收据保持冻结。summary离线重算热中位/P95并与原report逐项一致，拒绝SQL/network，确认临时目录已不存在。benchmark输出保留全部8个样本、XLSXhash及终态；资源原件保留全部668读数和32个阶段读数，parent收据证明退出码0/未超时。

- `summary.json` SHA256：`478e5f770177946b6744a1ae37efbcb485214b991a3110ab1aa65236c91d30df`
- `resources.json` SHA256：`de453fd19bcefb59da13687d038517163411b17b2e01a3d2376ae13f793747da`
- `benchmark.json` SHA256：`fca37fb0a78747539ec3a43817ede787cc9fbb14ead03ac1f56d95d3879f05c9`
- `parent-receipt.json` SHA256：`057ccda0870a22929535eb07f662f29bbb9ed806fb0f73a4b055f38e312ae78f`

该实测补充AI-T16资源证据，不改变共享状态、不代表整体功能或实际部署验收完成。

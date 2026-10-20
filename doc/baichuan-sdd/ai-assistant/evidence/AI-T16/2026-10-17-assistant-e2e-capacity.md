# AI-T16 确定规则任务到 XLSX 的隔离容量验收

2026-10-17，本机 Windows 11 / Python 3.13.16 / SQLite 3.53.1 / openpyxl 3.1.5，8逻辑CPU。1000/5000家均为明确命名的虚构企业，每家一个虚构ITSS证书；一半证书有完整虚构核验信息、一半未核验。单worker串行，无真实企业资料、常驻服务或目标数据库访问。

## 实际链路与隔离

新增可复现脚本：[benchmark_assistant_e2e.py](../../../../../scripts/baichuan/benchmark_assistant_e2e.py)。清除继承业务环境，在 `.runtime/baichuan-checks/assistant-e2e-*` 新建临时SQLite和存储；完整迁移/seed仅此新库，finally关闭连接后清理。父进程设置硬超时，失败保留已完成样本收据，拒绝覆盖既有收据。模型、搜索、研究、事实写入均关闭，socket连接/DNS与worker模型入口为异常守卫；ModelCallLog为0。

每次经过真实 `submit_message`、队列任务、`run_one`/租约、`save_match_snapshot`，然后通过导出消息入队、第二次 `run_one`、真实XLSX生成/受控落盘、`open_export`权限与哈希检查，最后openpyxl重新逐行读取三张表。确定条件通过真实可恢复检查点进入worker，**排除模型理解、HTTP/浏览器、公网与OCR**，不把合成条件称为自然语言验收。查询因研究禁用正常为partial且保留能力缺口，导出必须completed。

每轮断言确认/候选各一半，快照无遗漏；XLSX确认表/候选表各N/2条，逐项依据N条，三表合计2N条全部读回，所有数据单元格均非公式。

## 性能与实际瓶颈

首次全量基线：[e2e-before.json](2026-10-17-e2e-before.json)。1000家匹配152.411ms、XLSX778.287ms、总1392.332ms；5000家匹配1075.967ms、XLSX11136.057ms、总13674.287ms。单样本不计算P95。

独立属性计时：[row-profile-before.json](2026-10-17-e2e-row-profile-before.json)。5000家XLSX12369.996ms，其中 `Worksheet.max_row` 扫描9178.083ms（74.2%）；1000家扫描291.353ms。openpyxl每次max_row需扫描已有单元格，原 `_row` 在每个新增行重复调用，导致明显超线性增长。

已获授权仅修 `baichuan_exports._row`：改用单次工作簿内、每张表独立的行计数，仍使用原 `_cell`；保留元数据/字段/顺序/三表候选分离/公式保护和行数上限，不依赖openpyxl内部属性。

相同快照/相同导出时间直接对照：[identical-snapshot-comparison.json](2026-10-17-e2e-identical-snapshot-comparison.json)。1000家旧行算法956.889ms、新算法489.034ms（1.957倍）；5000家10736.977→2687.476ms（3.995倍）。同一环境内顺序比较，逐字节断言三张sheet XML、styles.xml和workbook.xml完全相同，结果计数相同；ZIP时间/核心属性可能随生成改变，不用整个压缩文件哈希要求冒充内容比较。

修复后的常规样本：[e2e-after.json](2026-10-17-e2e-after.json)。每规模1个关闭Django连接后的首样本及3个热样本；最近秩P95为3个热样本的最大值，样本量不足以推断真实总体尾延迟。未清除操作系统缓存，不能称为OS冷缓存。

| 分段热样本P95 | 1000家 | 5000家 |
| --- | ---: | ---: |
| 结构化匹配 | 255.054ms | 1148.658ms |
| 消息到固定快照就绪 | 356.691ms | 1275.632ms |
| XLSX构建 | 710.044ms | 3250.234ms |
| 含授权下载及三表重读的总耗时 | 1429.689ms | 5507.570ms |

对照AI-FR13：本次千家结构化P95低于2秒；模型排除后的首快照低于5秒。五千家整个导出链路约5.51秒，规格的5秒目标指首批可展示结果，不是Excel完成时间。以上不证明真实自然语言、OCR、公网、并发或目标部署达到目标，AI-T16/AI-AC17整项不能据此标完成。

## 回归、重现与边界

`check_backend.py portal.tests.test_baichuan_exports portal.tests.test_baichuan_integration_review portal.tests.test_baichuan_conditions portal.tests.test_baichuan_assistant`：**54项 / 41.807秒 / OK，无skip**。覆盖导出权限/撤权、固定快照、候选分离、公式文本保护、幂等、文件损坏、失败发布清理、租约/fence与新增三表独立行数上限边界。原始输出在私有 `.runtime/baichuan-checks/e2e-export-regression.log`。

首次小样的证据scope未设置为专用scope，被真实matcher拒绝确认为满足；修正虚构fixture scope后才取得完整通过，不放宽匹配规则。首次回归误填写不存在的test_baichuan_matching模块，整体退出1，未计为通过；上述正确四模块重新完整通过。

常规命令：`.runtime/company-test/python/Scripts/python.exe scripts/baichuan/benchmark_assistant_e2e.py --sizes 1000 5000 --warm-samples 3 --wall-seconds 180 --output <不存在的JSON路径>`。所有单轮命令均受硬限制，未运行实际服务重启、前端改动、浏览器、模型或真实企业查询。

恢复点：同快照旧新行算法的XLSX/XML比较收据单独保留；下一步仍为慢网/并发/OCR与部署资源竞争的独立验收。共享任务状态和检查点由主执行者根据本证据合并。

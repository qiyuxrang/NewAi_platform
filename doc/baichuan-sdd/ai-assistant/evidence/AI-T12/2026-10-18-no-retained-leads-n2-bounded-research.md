# AI-T12 N2：无可用留存线索分片的有界具体字段研究

执行时间：2026-10-18 02:27–02:34（北京时间）。研究与候选准备完成，未执行入库。不是全字段终态或工商/发证核验。

固定选择文件 SHA256 `325ef186a48b6bff774d8937f57e61d3f2297a686fd30099581cacf1ed7b8c68`；实际键 `no_usable_retained_lead` 共592项，本单位严格选取 `[20:40]` 的20个ID。独立离线核账通过：顺序与固定切片一致，20个ID唯一，与N1的 `[0:20]` 无交集。执行前和冻结前均仅以 SQLite `mode=ro`、`query_only` 读取当前ID/名称/version/空字段；20行选定字段保持一致。

## 实际执行及结果

- 每家1次新查询，共20次具体字段/所在地查询，原搜索完整字符串与逐组意图收据留档；与此前全称发现分开计量。搜索摘要只作线索。
- 6次公开固定URL GET，正常TLS验证，超时12秒、每响应2MiB上限、并发最多2，无自动重试/跳转；每家实际最多1次GET，未耗尽2页预算。
- 4家公司有非空可见正文；另1次HTTP200返回0字节，1份目录HTML的body显式 `visibility:hidden`。两者不计可见正文成功；原字节/hash均保留。
- 1个计划URL因该host已有确定失败而跳过；其他历史名单、采购聚合摘要、专利旧地址、不同名称企业没有强行跟随。
- 1家公司2个空字段候选：地址1、省份1。来源为企业目录实际公司名称/公司地址段，显式 `publication_kind=directory`；既有城市不覆盖，平台400热线、其他岗位联系人不收录。
- 两份招聘页存在标题/介绍主体混用，字段保留未知。2024商会新闻的相邻律师地址、新闻平台邮箱均排除。目录内显式HTTP站点仅保留为线索，本轮未改协议、猜官网或将隐藏脚本数据当可见联系正文。

`validate_batch` 实际PASS；校验时阻断SQL连接及socket，未调用模型/真实写入路径。后续离线复核30份原件/正文/意图/搜索文件hash全部PASS，固定切片与N1互斥PASS。模型调用、业务库写、前端/服务更改均0。候选只待根执行者审阅，当前不宣称已补入。

## 恢复文件及SHA256

以下私有路径均相对 `.runtime/baichuan-ai-local/independent-enrichment-20261017/`，不包含密钥：

| 文件 | SHA256 |
| --- | --- |
| `cohort-no-lead-n2.json` | `bb9cdf2a4b6e8fba2a50d2eaac7828ce6a5afef0a155eab26921b02c55c536fc` |
| `research-no-lead-n2.json` | `7dccad975787a5a053a74a25476e3366c3e08564911719203ec8d8fc27ac7fba` |
| `batch-no-lead-n2.json` | `1f29c8b7b27b6ac5033d1f133285aa4f01819aa91c1b2809d95b09b2f9b79277` |
| `no-lead-n2-final-receipt.json` | `d941f83174e4e59f9945e211d2b1408c766d647dd30e2ba44326ce1c4d18f030` |
| `no-lead-n2-offline-final-audit.json` | `12880ab461223fb3de9141f2b62ef242053e06f12661c5a4e0f0022b42d45a2c` |

复现入口为私有 `prepare-no-lead-n2.py`、`begin-no-lead-n2-search.py`、`read-no-lead-n2.py`、`finalize-no-lead-n2.py`；有界查询的实际收据位于 `no-lead-n2-search/`，正文/HTML及每URL意图位于 `no-lead-n2-raw/`。冻结文件已有独占创建保护，不应重复执行联网研究；恢复先核hash、读逐家缺口与候选，根审核后才走现有受控维护。运行环境复用 `.runtime/verification/Scripts/python.exe -X utf8`，现有HTML可见文本解析器；无新依赖或外部代码引入。

尚未完成：其余19家本轮没有安全字段候选；全部20家都不是12字段已补齐，证书与工商核实数没有增加。无结果或访问局限不表示企业不存在或没有资质。共享任务、检查点和全库覆盖索引由根执行者统一更新。

# AI-T12 L11 与固定 206 条覆盖核账

2026-10-18 02:21–02:23（北京时间）完成 L11 及独立离线集合核账。**L11 只准备 2 家 3 字段候选，未入库。L1–L11 的固定 206 个旧线索 ID 已完成有界复核，覆盖/互斥检查通过。** 不把该结果称为十二字段终态、所有企业均有正文、工商/发证核实或全库资料完成。

## L11 实际范围和候选

已核原 `website_blank_candidates` 恰有 206 条；L11 严格取 `[200:206]` 的 6 家，未扩展。3 次实际公开 GET：2 次取得 HTML 原件和正文，1 次 BOSS 原生 302，未自动跟随或重试。其他来源仅为历史名单或非联系用途线索，保留缺口，没有以摘要代替正文。

- 陕西拙实实业发展有限公司：市 `西安市`；[实际招聘页公司简介](https://www.zhaopin.com/jobdetail/CC481864080J40953855308.htm)明确“总部位于陕西省西安市”。没有从岗位城市推总部，遮蔽工作地点未还原，既有电话不覆盖，HR/平台联系排除。来源为企业资料目录披露。
- 陕西海泽天成信息科技有限公司：地址 `陕西省西安市高新区科技三路融城云谷B座501A`、市 `西安市`；取[百科基本信息首段](https://m.cbi360.net/baike/3437079.html)的完整目标全称和地址。下方包含其他企业模板链接，已完整留档并注明，不参与候选字段依据；未升级资质或工商核实。

两家 `expected_version=1`。结束只读复核所选 6 家版本与联系字段，均与起始相同；调用既有 `validate_batch` 时禁止 SQL/网络，实际通过。正常 TLS、每家最多 2 URL、读取最多 2 并发、12 秒/2 MiB 上限。0 新搜索、模型调用、业务库写入、前端或服务改动。

私有目录为 `.runtime/baichuan-ai-local/independent-enrichment-20261017/`：

| 冻结文件 | SHA-256 |
| --- | --- |
| `cohort-leads-l11.json` | `10805abc8ae78136f5f2b33c0bbf53bbc375c2e29753737ce7d7c7cfbc6a97c7` |
| `research-leads-l11.json` | `32e6fcb1bede2c6500822b9399fedf5657f3700c881a9d85dff3c5c6f6f7e0cf` |
| `batch-leads-l11.json` | `7576df15a15ebaba9d3ee36066bcb1983a7941df3ab60c1e106b9f0ecc86b3c9` |
| `leads-l11-final-receipt.json` | `a0614bb739fcef8ee8809234d838f5c8c76ef415142d8f3434d7b308493b0d58` |

实际脚本为 `prepare-leads-l11.py`、`read-leads-l11.py`、`finalize-leads-l11.py`，解释器 `.runtime/verification/Scripts/python.exe -X utf8`。原档保存在 `leads-l11-raw/`。冻结后勿原样重复网络阶段；应用只由主执行者在最新空字段、版本与备份预检后决定。

## 固定 206 条离线核账

独立脚本 `audit-fixed-206-leads-coverage.py` 不连接 SQLite/ORM，不发网络或模型请求。逐波检查原 selection SHA、cohort 精确有序分片、journal ID、cohort/journal/最终 receipt 相互绑定 SHA，以及候选批次 SHA。前 10 波每波 20 条，L11 为 6 条；合计 206 条、206 个唯一 ID，重复/缺失/越界均 0。

L10 起初按未最终确认处理。收到负责代理最终冻结确认后，实际核对 journal、`leads-l10-freeze.json` 和最终 receipt 三份指定 SHA 才纳入完成。离线边界练习也实际通过：移除 L10 后缺 20 个完成 ID；故意插入一个重复 ID 时检测到重复，不能仍称完整互斥通过。L4 没有 `frozen` 布尔字段，使用其完成状态、结束时间及已冻结最终 audit 对 journal SHA 的绑定作为完成证据。

最终机器清单 `fixed-206-leads-final-inventory-20261018.json` SHA：`d1520279d85d8e56d3573fdc1173a399aa6d877d2897cf63bd71dbf3408c3603`。清单包含每波 206 个固定 ID 的归属、各文件 SHA 与完成时点；候选数量不等同实际入库数量。

供中心索引恢复的零候选批次已单列，未修改其任何字节或重复请求：

| 波次 | cohort | 实际请求 | 实际正文企业 | 候选字段 |
| --- | --- | --- | --- | --- |
| L1 | 20 | 5 | 3 | 0 |
| L2 | 20 | 4 | 3 | 0 |

- `research-leads-l1.json` SHA `dec7c9950ec9a68f547acebd1fc3919ae71678cf6ea715032861d906deec0c38`；`leads-l1-final-audit.json` SHA `efe1acb66c429adb1be140bcd8b3f49f52c58ab3dd3dae5ac7ded21850b44314`。
- `research-leads-l2.json` SHA `bf264145d0253d76ad3d612f27b2d242c12f7b5051f0eb10d23657294d7e0ff4`；`leads-l2-final-receipt.json` SHA `72eda6230aa3fc053718590628453bc4210a159c0ac6ad13afe63c51fc67e335`。

历史 `public_body_read_companies=148` 保持原口径，未重算全 journal 并集，也没有把各波正文数量直接加上去。该清单只可恢复固定旧线索的覆盖索引；当前字段覆盖、实际入库批次、全库研究队列与原成果保护，仍由主执行者独立核账。本单元不修改共享检查点、进度、任务或覆盖索引。

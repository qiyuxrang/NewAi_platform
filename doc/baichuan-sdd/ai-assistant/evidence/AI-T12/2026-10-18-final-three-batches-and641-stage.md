# AI-T12：后续三批实际维护及641字段阶段状态

本文件记录根代理实际审核、维护与核账，不把候选收据当实际写入。

| 实际批次 | 公司/原空字段 | 实际结果 |
| --- | --- | --- |
| 第四官网12组目录资料 | 众望能源，地址及字面城市2项 | 06:52:03 实写2/重放0；目录不升级为官网，松毅HTTP200空模板不补官网 |
| 最后电话8组 | 陕西裕方，电话/邮箱/地址及根独审字面省份4项 | 06:52:25 实写4/重放0；保留原城市；号码未经拨打，目录不作工商核验 |
| 第五官网12组目录资料 | 煤科透明地质地址/邮箱、东晶测控地址/城市4项 | 06:53:04 实写4/重放0；CMMI目录不作证书核实，西咸地址不猜城市 |

每批均先离线验证正文、法定全称、字段字面定位和原始raw/body SHA，再通过既有维护工具在线备份、版本CAS和企业事务补空。各实际收据如下：

- `.runtime/baichuan-ai-local/independent-enrichment-20261017/untargeted-website-next12-fourth-20261018-0644/root-actual-two-fields/receipt.json` SHA256 `2308d3d557f03f8fe0d3034b7e757ea4229ff6a8fda027cc0cbdf6839b1a3cf7`；apply 2/replay0。
- `.runtime/baichuan-ai-local/independent-enrichment-20261017/untargeted-phone-final8-20261018-0646/root-actual-four-fields/receipt.json` SHA256 `5a56cd8a84a1f5f0dd78f08f89269915c38a08ce476cecf75f87f7740f86ce32`；apply 4/replay0。
- `.runtime/baichuan-ai-local/independent-enrichment-20261017/untargeted-website-next12-fifth-20261018-0648/root-actual-four-fields/receipt.json` SHA256 `e1696f76a895f7e52546bc0d42f81e096851d1659c432556776492b84bf251e8`；apply 4/replay0。

加上此前[页脚及第三官网组5字段](2026-10-18-footer-and-thirdwebsite-root-maintenance.md)，本阶段共5批15字段：电话1、地址8、邮箱2、省份1、城市3，官网0。68个互斥ID各1次目的查询（68查询/17工具调用），新增正常TLS GET共9次（含远眺显式同源页脚1次），模型0。网站36家未知并不表示不存在官网。实际计数和去重ID由根离线重核：

`.runtime/baichuan-ai-local/night-acceptance-20261018/continuation641-final/purpose-and-maintenance-reconciliation.json` SHA256 `f1b679f6a25300c90326ad573ad53f1c597d6a7f1219029a05982862805cb8e8`

截至最终保护检查，95维护批/295家/641原空字段；实际1283家，官网105（8.18%）、电话1035（80.67%）、地址270、邮箱115、省份1096、城市696。原1024电话保留，新增11个公开号码未拨打。1460原资质声明和162公开ITSS观察均未独立发证核实（0）。12字段全完成企业0；研究队列15396项、15384待处理/12不可达，不能以网页研究轮次改为完成。

`.runtime/baichuan-ai-local/independent-enrichment-20261017/night-batch-preservation-20261018-065305.json` SHA256 `034a01d3137377afcd1275fec09632d0c9fccadd09f429111a34f72061f93c72`：41685原行、原非空/人工值、28旧快照、162观察及163前端保护PASS；quick_check通过。

`.runtime/baichuan-ai-local/independent-enrichment-20261017/field-gaps-continuation-20261018-065321.json` SHA256 `2fdc441a09e3f1ebb8cd9134ce4026f78fe6a2dc8dd7418b1c085cc090dd3dac`

[249空电话目的审计](2026-10-18-current-empty-phone249-purpose-audit.md)冻结分母249：193明确电话查询、55仅混合OR、1号码专项复核；20家公司缺原始搜索档绑定，不升级为独立工具证明。根实际复核37个冻结输出SHA及249唯一ID，并以当前RO数据库过滤只移除本次已补的裕方，现仍空248家。55家可用新的电话目的查询/来源策略接续；不得重复旧查询。培荣连续号码仍待独立核实，不制批。

626字段独立组合审计只覆盖冻结90批/288家公司；后续15字段由本阶段实际维护证据承接，不冒称已加入原独立全链复审。新增13逐条复核与旧613沿用范围见[独立组合证据](../AI-T18/2026-10-18-new13-lineage-and-composed626-independent.md)。

前端无改动/构建/重启，无远程写入、清库、采购或企业联系；普通查询仍不自动补查。全库资料、核实与最终交付未完成。

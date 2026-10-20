# AI-T15：失败验收追加记录的精确保护

本单元仅修改私有维护记录工具 `.runtime/baichuan-ai-local/record_night_batch.py`，未执行其 `main`、record命令、资料apply或v2浏览器。主库只读；业务源码、前端、服务、原失败脚本/收据、共享SDD状态均未修改。

新增 `reviewed_offline_failure(current)` 限定原单元真实追加：会话1、消息2、job1、快照1、模型日志1（id26 success），认证session新增0。固定原FAIL SHA `d62a90e2ee336f63967cc72d6c34200212d38e9fd9338dbcd538d3d023881f61`、后审SHA `d814290eb1f99d647516dc16503ea2cea3b1f68e54feeca9018044bf2247c14f`、nativeUUID和全部新增ID；上述6行逐条完整行SHA固定，不能仅以数量相同放行替换ID或改值。

额外绑定实际第80维护批前在线备份 SHA `f2a085a0e9ea6f6a0ed2dda34138fa89e35b6068af4efad66d13faaf117f8287`，与当前库逐行比较全部既有conversation/message/job/snapshot/model/attachment/export/session：旧28会话、24快照、25模型日志、34session及其他旧行完整保留。24旧快照另逐个检查四字段SHA。原第1批前的41685原记录、原非空和人工值保护逻辑保持。

累计夜间允许追加数仅作精确增量：model18→19、conversation17→18、message36→38、job22→23、snapshot18→19；attachment12/export4不变。新快照 `1c7ba717-9674-4ca0-8c86-a6a959a0b24e` 四字段SHA `2334a60bf70778c9e1a55e883dc717ad774ca81c539d4b47ac3c0dbbaddd87ab`。原FAIL、实际离线刷新、重连 **NOT_RUN** 被独立记录，不增加恢复PASS或源码变化白名单。后续任何新验收仍需再次显式扩展，不能自动放行。

独立核账命令：

```powershell
& 'C:/Users/YLJJT/AppData/Local/Python/pythoncore-3.14-64/python.exe' .runtime/baichuan-ai-local/night-acceptance-20261018/product-offline-protection-review/audit.py
```

结果：1项真实所属库只读正例、3项内存负例通过。负例分别注入未知job ID、修改旧snapshot完整行、修改批准新增message内容，均被拒绝；没有在SQLite写入这些负例。单一只读事务中6张表前后SHA一致。当前实际计数conversation29/message69/job47/snapshot25/model26/session34。早期核账脚本的括号语法错误，以及初选空快照把 `[]` 改为同值而未构成篡改的测试构造错误已修正；不是业务失败或放宽门禁，最终使用明确不同marker验证拒绝。

产物：

| 文件 | SHA256 |
| --- | --- |
| `record_night_batch.py` | `46428da6888d7d7664ea22f0939cfb4c377b57572651e3f04197b095e47b96e6` |
| 私有 `product-offline-protection-review/receipt.json` | `564b86a2ce796c579d5a399a88a91aa91a16c5d0565d48d06553d1dda5021331` |

本记录只证明上述保护函数、当前固定记录和负例。没有执行整个维护记录命令，没有更新coverage或宣称全库资料完成。

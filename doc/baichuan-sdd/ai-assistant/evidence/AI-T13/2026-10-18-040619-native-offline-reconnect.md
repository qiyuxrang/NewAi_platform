# AI-T13：product原生离线与重连刷新实际通过

实际时间2026-10-18 04:06:07–04:06:19（北京时间）。独立无头Edge，原product账号原UI登录和纯文字提交各1次，未操作用户浏览器。脚本 `product-offline-reconnect-v3.py` SHA256 `204d52880c12229fd3163ea9e5aa85ce8fe8c8f11fdca0658c52c32bb42169f3`，9项默认/拒绝/owner/协议边界隔离检查通过后，根独立审核授权执行；原v1/v2 FAIL均保留。

绑定所属加载收据 `certificate-reconciliation-owned-backend-load/receipt.json` SHA `d34e75b19fde40b56297ff5b302675a7506edf14d9c8f6774b7e33a15d54c01d`，360项隔离回归版本；执行前实查5owned进程身份，frontend PID21632和163文件指纹保持。没有修改前端、后端源码、运行库或服务。

实际链路：原UI提交前先持久化nativeUUID；收到202立即保存原owner助手key/cid；queued时同一存活context实际set_offline(True)与page.reload，记录ERR_INTERNET_DISCONNECTED。离线错误文档的CDP原origin存储读取实际不可用，按已独立复现机制记null/unavailable，未伪造存储值、未关闭context。随后仅RO等原job completed，set_offline(False)并在原page真实reload；页面默认收起，打开后恢复同一cid/jid/sid与原消息/结果，固定快照列表和返回原20行列表均通过。beforeoffline与afterreconnect原native存储严格相同，没有注入cid、cookie、token或DOM补丁。

纯文字“投标人必须具备ITSS二级资质，要求精确二级。结果字段为企业名称和电话。”实际得到ITSS grade_exact2/bidder、1283candidate/0confirmed，未知不满足；研究策略独立任务，query来源预算0。唯一Model28 success，2937ms，1118输入/227输出token；attempt1、模型预算1，未重试/研究/上传/导出。实际新增conversation1/message2/job1/snapshot1；认证session34→34/新增0，旧session完整行保留。全26旧snapshot四字段与完整行、旧会话/消息/job/model、企业/资质/人员、研究计数和163前端均保护。累计模型28、快照27、会话31。

私有目录 `.runtime/baichuan-ai-local/night-acceptance-20261018/product-offline-reconnect-v3/`：

| 冻结产物 | SHA256 |
| --- | --- |
| 原 `receipt.json` | `d08aff2e290e6835dab8ec8dd86e5e451cb1eee2c0cef3735cae7bf40a6aa8ef` |
| `post-readonly-receipt.json`（精确IDs/六行完整SHA/全旧快照SHA） | `a98ced1a4459cdac947b84e978cbd699866f232ee5798705a62efa30161fcc00` |
| 新快照四字段 | `f9c5b8359e82531c831ce74584b535e437aabc750ca5f74f1a97ff1f671f0fe1` |

会话 `61ed8d2d-4f5c-4022-b6d9-e6b74d8a771f`、任务 `0d03f13b-c61a-41fc-8680-514c9d9c79e0`、快照 `4cc19b92-7598-4348-a355-b10a2a9d1ea5`；四字段算法与既有GM收据一致：SQL行condition_tree/results/counts/fact_cutoff_at按sort_keys/ensure_ascii=False/default=str序列化后SHA256。

退出码0，完整观察和最终RO核账均PASS。Playwright在正常browser.close后仍输出两个Response.finished后台任务Target closed警告，原输出保留，未修改运行库或把警告隐去；未影响实际完成记录。此结果仅属于本product新原生会话的离线重连恢复，不能升级GM离线格或声称离线应用外壳可用；两次原失败/GM旧表格刷新NOT_RUN不改。全库研究、证书核实、远程部署状态另行验收。

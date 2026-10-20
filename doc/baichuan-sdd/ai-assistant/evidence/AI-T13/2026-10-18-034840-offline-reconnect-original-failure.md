# AI-T13：原生离线刷新已执行，重连链因验收器失败未验

取样时间：2026-10-18 03:48:33–03:48:40（北京时间），最终既有任务另作只读核账。前端、后端源码、服务、企业资料均未修改；仅独立无头 Edge 原页面操作。

原执行脚本 `.runtime/baichuan-ai-local/night-acceptance-20261018/product-offline-reconnect.py` SHA256 `c95eb6c3d1acab94a86f525907ec30b34666381f0a00cb5b9902b76fc2f373b7`。准备时5项隔离检查通过，默认 SQL/HTTP/模型/登录均0。实际唯一执行：

```powershell
& 'C:/Users/YLJJT/AppData/Local/Python/pythoncore-3.14-64/python.exe' .runtime/baichuan-ai-local/night-acceptance-20261018/product-offline-reconnect.py --execute --expected-model-count 25 --expected-snapshot-count 24 --expected-session-count 34 --expected-conversation-count 28
```

实际原页面登录1次、会话1个、纯文字提交1次；原生 request UUID 在放行 POST 前落盘。真实202后已保存当前 owner 的助手 localStorage key/cid，任务为 queued。随后在同一存活 context 实际 `set_offline(True)` 并 `page.reload`，得到 `ERR_INTERNET_DISCONNECTED`，没有声称离线应用外壳可用。

原验收器失败：迟到的 `/api/auth/me` response 事件在页面导航后读取 `response.json()`，Playwright 返回 `Network.getResponseBody: No resource with given identifier found`。该非关键迟到事件异常打断后续取证，finally 关闭原临时 context；after-offline storage 与重连刷新恢复均 **NOT_RUN**。这是验收器时序错误，不能当作产品业务失败，也不能把另建 context、注入 cid 当作原生恢复。未重发、未自动重试。

唯一原任务后台实际 completed。后续仅使用所属 SQLite `mode=ro/query_only` 读既有任务，0HTTP/模型/提交，核对投标人 ITSS 精确二级、1283候选/0确认、预算模型1/来源0、attempt1。最终新增会话1/消息2/job1/snapshot1/模型日志1（id26 success）；认证 session 34→34/新增0。全部24既有快照四字段 SHA、原会话/消息/企业/资质/人员摘要、研究计数与163前端指纹保持。

私有目录 `.runtime/baichuan-ai-local/night-acceptance-20261018/product-offline-reconnect/`：

| 冻结产物 | SHA256 |
| --- | --- |
| 原失败 `receipt.json`（保持未改） | `d62a90e2ee336f63967cc72d6c34200212d38e9fd9338dbcd538d3d023881f61` |
| `post-failure-readonly-receipt.json` | `d814290eb1f99d647516dc16503ea2cea3b1f68e54feeca9018044bf2247c14f` |
| 新快照四字段 | `2334a60bf70778c9e1a55e883dc717ad774ca81c539d4b47ac3c0dbbaddd87ab` |

新快照 id `1c7ba717-9674-4ca0-8c86-a6a959a0b24e`；四字段算法为 SQL 行 `condition_tree/results/counts/fact_cutoff_at` 的 `json.dumps(sort_keys=True, ensure_ascii=False, default=str).encode()` SHA256。精确新增 IDs、原生 owner 存储、原失败阶段、来源与保护标记保存在私有收据，不含密码、token、cookie。

剩余最小单元：新独立原生会话，在导航之前显式等待并完成原认证响应读取与 owner 验证，移除非关键 response 读取回调，再以固定新 native UUID 验证同 context 离线→重连真实刷新。原失败单元及 NOT_RUN 不修改。本记录不升级 AI-T13/T17 整项或全库资料完成状态。

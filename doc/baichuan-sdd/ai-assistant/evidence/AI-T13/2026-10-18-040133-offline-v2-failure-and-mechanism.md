# AI-T13：v2原失败与无业务错误页机制验证

v2实际执行于2026-10-18 04:01（北京时间），使用已审核脚本SHA `5de715f5faaa32bf9038ff93ff81fe10db812a7152db69911dbb8a72de62e554`，绑定03:59:27所属后端加载收据SHA `d34e75b19fde40b56297ff5b302675a7506edf14d9c8f6774b7e33a15d54c01d`、360回归通过版本。5进程创建时间/命令/executable身份实查owned，frontend PID21632及163指纹不变。首个只读预检误将processes列表当对象，未开始浏览器/认证/SQL，修正读取类型后实际预检通过；不是业务失败或额外查询。

唯一原生登录、会话和文字提交成功；认证原响应已在导航前明确读取、实际owner校验成功。202后原native key/cid已保存，queued时同context实际离线刷新得到ERR_INTERNET_DISCONNECTED。随后读取错误文档的原origin存储时抛Error，原脚本finally关闭context；afteroffline存储及重连刷新 **NOT_RUN**。原失败状态不改、无自动重发或v3执行。

原job后台completed，模型id27 success且attempt1、模型预算1/研究来源0。独立RO核账实际新增conversation1/message2/job1/snapshot1，认证session34→34/0，模型总27、快照26。投标人ITSS精确二级、1283candidate/0confirmed均已从既有任务验证。全部25旧快照四字段SHA、原会话/消息/企业/资质/人员及163前端保留；这不等于重连链PASS。

私有目录 `night-acceptance-20261018/product-offline-reconnect-v2/`（均位于所属 `.runtime/baichuan-ai-local/`）：

| 产物 | SHA256 |
| --- | --- |
| 原 `receipt.json` | `58607a911d9f6a931ad91d8a866e960ef19621b6a299ce545098b8e26db6f132` |
| `post-failure-readonly-receipt.json`，含全部新增行完整SHA与精确IDs | `d603b18ed19558bbc8cd318cf08272c43e003e0d2d184977b88e21248edffa2b` |
| 新snapshot `40b4a53c-abc8-4a54-b1c7-3aa3a5c9201f` 四字段 | `0773484458f6ce564e3030d15b26016bf69482bdebdc947839ad06852683be62` |

根随后授权仅作浏览器机制预检。新临时127.0.0.1随机端口HTTP fixture，HTML首次自己写入无业务含义的mechanism-test-marker；同一context离线reload后，**真实复现**：`CDPSession.send: Protocol error (DOMStorage.getDOMStorageItems): Frame not found for the given storage id`。未关闭原context，重新上线并真实reload，原marker读回，第二个HTML响应不写marker；所以这是错误文档读取原origin存储的机制限制，后续重连可继续验证。该机制实验0认证/主库SQL/模型/业务HTTP，没有注入任何assistant cid、token或cookie。

机制收据 `night-acceptance-20261018/offline-storage-mechanism/receipt.json` SHA `0fbff5e5ab8745f79531e3842b3b36f3a96d6dc1424b39d67c9078f453098d23`，保存浏览器版本、真实URL/origin/协议错误、原页/原context与两次fixture请求；临时服务已停止。

v3已独立准备，9项隔离检查通过：仅已复现的指定CDP错误记unavailable，不关闭context；无关Error或owner/key断言仍拒绝，重连后仍须严格原owner/cid/jid/sid。默认0SQL/HTTP/model，未实际执行。原两次失败及各自NOT_RUN全部保留；AI-T13/T17整项由根按证据统一审核。

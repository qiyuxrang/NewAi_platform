# AI-T15：AC02 原文两轮原生页面验收

实际执行时间：2026-10-18 09:15:36.667201—09:16:05.439393（UTC+08:00）。本单元结果 PASS：产品工作台原页面完成 AC02 指定原文的两轮查询，硬性 AND 条件与精确等级保留，追问追加广州和电话输出字段，同一原生浏览器上下文真实刷新恢复当前会话、任务、快照及条件版本。仅说明本次固定输入的实际行为，不外推模型的全部理解能力。

## 输入与实际结果

原页面依次提交，未修改措辞、未补发任务：

1. `广东电子与智能化二级且 ITSS 二级`
2. 同一会话：`只要广州的，加上电话`

第一轮 `must.all` 同时包含广东省、投标人电子与智能化 `grade_exact=2`、投标人 ITSS `grade_exact=2`；两项资质均为硬性条件，未变为 OR 或优先项。第二轮继承上述三个条件及其真实用户消息定位，再加入广州市条件；`should` 和 `unresolved` 均为空。新定位来自本轮真实消息，未伪造附件来源。

第二轮 `output.fields=[name,phone]`，API 返回的实际结果企业结构包含 `phone` 字段，未增加电话存在或非空的硬性过滤。第一轮默认输出原本已包含电话，不能将本轮描述成首次获得电话资料。两轮结果分别覆盖在库 1283 家，确认集合与只读核对的原库双资质精确二级及地区交集一致；该交集实际为空，不人为要求出现已确认企业或非空电话号码。

| 轮次 | 原生任务 ID | 固定快照 ID | 已确认 / 待核实 / 排除 |
| --- | --- | --- | --- |
| 第一轮 | `195703e6-abb7-466c-9a8b-58b931b5456e` | `1f02b571-ae0b-40d7-952b-6abc52f29c62` | 0 / 187 / 1096 |
| 追问 | `5755622c-b77b-43be-a27d-120dabc814a6` | `b09a710e-50eb-4757-82c1-043ed4b8419c` | 0 / 1 / 1282 |

会话为 `7cc2a116-31a8-4ed7-86ca-37673f54214e`。两个原生请求 UUID 在 POST 放行前持久保存，分别为 `810fbc37-de81-413b-acfd-fd587fcf5fdd`、`4da42b1f-7667-40ab-b3e4-3b76fbe7d194`。刷新恢复条件版本 2 和第二轮任务、快照，两轮消息仍可见；没有手工注入助手会话 ID。原生“在列表查看”显示条件版本 2 和第二轮快照标识。对应截图捕获到固定列表的读取中状态，不能将该截图说成列表企业卡片、电话值已经完成加载；电话输出的断言来自实际结果 API 的条件与企业字段。

## 版本与证据绑定

本轮使用 Edge `155.0.4283.45`、现有 Python 3.14、原工作台 `http://127.0.0.1:13180/departments/product/baichuan`。浏览器网络仅所属本机服务；模型使用已配置网关。前端源码、DOM 实现、样式、构建和所属服务均未修改。

私有目录统一前缀：`.runtime/baichuan-ai-local/night-acceptance-20261018/`。以下原件均保留，SHA256 于收束时重新读取核对：

| 文件 | SHA256 |
| --- | --- |
| `ac02-literal-native-20261018-attempt4/verify.py` | `81157e4e77681916eafebc99ecafb9240933fb76cfcee7a4eff1bf5da2d6639c` |
| `ac02-literal-native-20261018-attempt4/final-receipt.json` | `307c253260f39534bf4d5a131171052c1ab459f95b95fb5936f10c3c2eaf9151` |
| `ac02-literal-native-20261018-attempt4/post-readonly-audit.json` | `0cc962c0552098c9547f67d6d7a7ba623ceafef8fb4fe858d93273c932e224c7` |
| `remaining-literal-final-readiness/receipt.json`（根代理 09:16:44 只读收尾） | `082a4ddd72012a262aa55342e4c60d534ec2c0494b6f43adeb0d66061c00f1a4` |
| `remaining-defects-final-regression-attempt4/receipt.json`（37 模块 463 项 PASS，248.323 秒） | `83849721138b1fb7e387bc1ad6c5fc901e41711d6c8ce3bc0c757cc6bc15e171` |
| `remaining-defects-owned-load/receipt.json`（08:59:37 后端加载） | `fbf0d782e0068807da156dacc200be11d8c7100b5d7b74a397e6111e28219e6a` |

快照四字段 SHA 使用 `condition_tree/results/counts/fact_cutoff_at`、`sort_keys=True`、`ensure_ascii=False`、`default=str` 的既定算法。第一轮为 `856dd0c9a093566a613bc7d10550d24b1209c383244aee0da71afbd495f0a721`；追问为 `83ae969038d2edfab9cfddfe48d9a4c322d70f4e24d87c32f1fa41b0b6622501`。新增完整行 SHA、消息 ID、真实模型行及原会话摘要详见独立只读收据。

## 实际增量与保护

新增 1 会话、4 消息、2 查询任务、2 快照、2 成功模型日志（39、40）；模型总数 38→40，快照 37→39，会话 40→41。模型输入合计 2549 tokens、输出 989 tokens；各请求仅一次，自动重试 0。附件、导出、资料研究调用均为 0，企业目录、原资质、人员、证书和维护事实写入为 0。

现有连接过期，本次经原 BusinessLink 页面“原业务账号 / 原业务密码”正常表单恢复所属连接，`/api/enterprise/link` 仅一次。新增 1 个正常认证 session，34→35，全部原 34 行完整保留；只允许所属用户的 `last_login` 更新，其他用户字段与其他用户保留。该操作与平台 API 登录分别记录，不称为平台登录表单验收；不公开 session key 或凭据。

独立 `post_readonly_audit.py` 仅使用 `mode=ro`、`query_only` 事务，未调用浏览器、HTTP 或模型。核对全部原业务数据、原 37 个快照及既有会话相关完整行、新增精确 ID/完整行 SHA、模型用量、用户/session 和 163 个前端文件指纹。实际 PASS。根代理另外完成最终只读收尾，本证据引用其收据，不冒称重复执行了根的核账。

## 保留的前置失败及边界

前三次仅验收器前置失败，均未发助手 POST、未建立查询任务、未消耗模型。原件未覆盖：

| 目录及 `final-receipt.json` | 原因 | SHA256 |
| --- | --- | --- |
| `ac02-literal-native-20261018/` | 验收器误将实际 `employee + department_code=product` 写成角色常量 `product` | `3300cbcc9c5eaa808255108b40adfb4e43b7c1f5c0a00373cbaf08b3895cc9d1` |
| `ac02-literal-native-20261018-attempt2/` | 在正常业务连接恢复前过早读取助手配置 | `38aa6f0e06bdafff1559d1ee88773de4ffb59757d39d2a1897a392e70684e1ad` |
| `ac02-literal-native-20261018-attempt3/` | 过期业务连接导致工作台助手入口未出现 | `cd4a12875f05085f17393f7586125e7fbe204970d8e7b8f610005f1820eeb2fb` |

第四次在精确核对真实产品账号、平台 owner、portal owner 与现有配置 schema，并正常恢复连接后执行成功。前三次不能计作业务失败，也不能删去或写成零认证活动；第四次的两次助手提交是本单元首次实际查询，不是重发已有任务。

本单元补齐 AC02 原文示例及原生追问恢复证据。旧响应晚到的原组件时序证据、实际性能目标和其他文件/OCR边界另见 [本轮 UI 与性能证据](2026-10-18-resumed-remaining-ui-and-performance.md)。真实首可见 8.2276 / 5.142 秒仍未达到 5 秒目标，不能用本次通过替代性能改进；本次也不扩大为全库资料补齐或远程部署验收。

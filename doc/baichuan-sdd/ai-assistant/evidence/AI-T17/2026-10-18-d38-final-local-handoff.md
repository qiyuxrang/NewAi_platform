# AI-T17：AI-D38本地交付收尾

AI-D38本地交付收尾完成（2026-10-18T20:29:09.533178+08:00）：47模块617项新回归PASS/322.841s/0skip/87输入；前端16项、TypeScript及助手ESLint通过。Edge双角色1920/1440/768/390共8视口、键盘焦点、可信浏览器组合输入及减少动画通过；支持范围为本机Edge，物理输入法候选窗口、Chrome/Firefox和原生无blur环境未验收。断网中文提示与保留草稿、恢复不自动发送、丢响应同键重提只产生一个任务、观察断流后任务继续、损坏PDF明确失败及原页面关联重试/显式文字替代/刷新恢复通过。修复损坏/加密等内容错误未进入未读附件恢复协议的缺口，基础设施/安全/限额错误仍独立保留。仅备份加载所属portal/worker（2026-10-18T20:24:31.910292+08:00），原前端21632与两网关保持，161其他冻结文件/CSS/布局/入口及原资料保持；93表在线备份与恢复副本全结构/全行摘要一致。速度和资料补全按用户要求延期，远程未操作；并非原SDD全浏览器/整机灾备全部通过。


任务AI-T13/15/16/17；验收AI-AC01/02/04/13/14/15/17/18/20仅本次实际子项，不批量放行原全部验收。


本轮实质改动：助手接收器仅将原生网络TypeError映射为中文可恢复提示，测试使用共享Error构造器验证真实异常；worker仅将5种明确的文件内容错误转入原附件未读协议，锁/租约/哈希、隔离解析、未知不满足和无自动补全策略保持。新增2项后端测试覆盖5种内容错误、8种基础设施/安全错误；现有文件替代/重试测试及全回归均实际执行。


首次native-faults失败：脚本把合法的幂等重提200误认为必须202，原日志与单消息单任务证据保留。native-faults-final失败：真实损坏PDF使任务invalid_document但附件pending，属于实际缺口；修复后只点原失败任务的显式重试，不重做已成功的检索。原失败任务及快照完整保留。模型超时与服务端会话过期/撤销在隔离真实session/worker边界验证，6项与完整617重叠，不相加，也不冒充真实主模型超时。


本轮累计新增4个不同任务、2个快照、1次真实模型；人工调用预算null，有限重试/超时/幂等/并发保护保留。没有额外模型健康检查、采购、企业补录或发证核实。原导出不变，没有重复生成已验收导出。


兼容性8用例在网络提示修正前执行；之后仅messageFor错误分支和对应测试变化，布局/样式/输入/焦点实现及161其他文件不变。当前源码16项与真实断网恢复重新验证，不把旧源码当新全浏览器验收。


恢复边界：本轮在线portal备份与恢复副本实际通过，未向主库恢复；私有代码包仅包含87个被测试输入，解压内容SHA逐项核对，不含env/账号/密钥/数据库/用户附件，不是独立整套安装器。完整工作区、原私有文件与两库协调恢复仍遵循local-operations.md，不宣称整机灾备。


恢复补验首脚本在写入任务前误等已隐藏的旧结果，FAIL保留；修正为等当前失败任务后才执行关联重试，成功检索未重复。UUID转录及CRLF/模型日志状态名的只读校验脚本误断言均在操作前修正，无额外任务/模型；并非应用功能失败。


兼容源码与真实用量绑定：`.runtime/baichuan-ai-local/night-acceptance-20261018/d38-local-handoff/compat-and-usage-binding.json`，SHA256 `62a44f54cbb340ccbe88abda13a17fb486bdb79c37563759a5d2808d4a5d8cbe`；当前助手删除新增3行并按原CRLF还原即可匹配兼容验收前SHA，无布局/焦点/输入代码差异。本轮唯一模型实际输入1477、输出120token。


- 私有证据 `.runtime/baichuan-ai-local/night-acceptance-20261018/d38-local-handoff/compat/receipt.json`；SHA256 `02fce699eada04858834e652e0248e7d3ffe68a45b58f961c051a2dd33031de1`。


- 私有证据 `.runtime/baichuan-ai-local/night-acceptance-20261018/d38-local-handoff/frontend/receipt.json`；SHA256 `0754c979f826dd9667992c7f03a25daddd48e36abe8ff044b62199a2249aceda`。


- 私有证据 `.runtime/baichuan-ai-local/night-acceptance-20261018/d38-local-handoff/isolated-exceptions/receipt.json`；SHA256 `469a989f772dc60f10eef1bfa7f304feff0f803dba051cc4b6276e52e1d1a83e`。


- 私有证据 `.runtime/baichuan-ai-local/night-acceptance-20261018/d38-local-handoff/regression-final/receipt.json`；SHA256 `fac15f06cc1cf1b8bc068388f8e4a2e5f925fee461857c7db366a39eff7652e3`。


- 私有证据 `.runtime/baichuan-ai-local/night-acceptance-20261018/d38-local-handoff/load/receipt.json`；SHA256 `27b59eb1e0080d372f03fadbd78950d1e356bd7e5642580ca4cc795d85691dc8`。


- 私有证据 `.runtime/baichuan-ai-local/night-acceptance-20261018/d38-local-handoff/native-faults/receipt.json`；SHA256 `4d80444fad6fe43d07fc5fa67d5021e315343afed18fd581aea43ffbec2443dd`。


- 私有证据 `.runtime/baichuan-ai-local/night-acceptance-20261018/d38-local-handoff/native-faults-final/receipt.json`；SHA256 `029c667d03373bb8caafba94d3e68b02569075e5b5114f9d6697c0f30161fd54`。


- 私有证据 `.runtime/baichuan-ai-local/night-acceptance-20261018/d38-local-handoff/native-recovery/receipt.json`；SHA256 `2e6e59b886da816acd01e96c936b5de89565567c58b5b2775ab389e21c3cfe37`。


- 私有证据 `.runtime/baichuan-ai-local/night-acceptance-20261018/d38-local-handoff/native-recovery-final/receipt.json`；SHA256 `89f96baaee62e034ab7fa94b0b8fefac7ed59fe89d5e49e6b8526dfb2010ad91`。


- 私有证据 `.runtime/baichuan-ai-local/night-acceptance-20261018/d38-local-handoff/operations/receipt.json`；SHA256 `9c32adaa97567af9817b306d8dadbf6c29d00bb710b09073e82f7419f10b8602`。

# AI-T17：AI-D39部署前兼容性与本地资料恢复

AI-D39部署前当前范围完成（2026-10-18T21:00:40.390306+08:00）：用户明确尚未到正式部署阶段，本轮未部署。新增Chrome for Testing155.0.8059.84与Firefox157原页面补验：两角色各4视口，另Firefox原生关闭blur能力，共24组视口/6组触屏仿真通过；两浏览器四组角色的原结果恢复、文件选择与移除、既有Excel下载及刷新通过。portal93表+platform6表、18451文件/1131103415B备份与恢复副本哈希一致；两角色密码/绑定/权限/结果/既有Excel及36份附件实际回读通过。0应用源码改动、0新查询/模型/导出生成、0构建/服务重启，163当前前端指纹与全部资料保持。D38的617项/前端16项为输入未变的历史有效检查，本轮不冒充重跑。真机、Safari、物理输入法及新机器整机冷恢复未执行；速度/资料补全继续按用户要求延期，不是当前交付前置项。


对应AI-T13/15/16/17；AI-AC01新增原生无blur与多浏览器实际证据；AI-AC02/12/13/14/15/18/20仅本轮实际子项。正式部署不在当前阶段，不再要求服务器作为本轮阻塞。


Chrome/Firefox正常与Firefox无blur各8个视口，覆盖1920/1440/768/390、两角色原平台登录及业务绑定、默认收起/右侧覆盖/文档宽度不变、开合焦点、Escape、ShiftEnter及减少动画。Firefox no-blur使用其自身首选项关闭能力，实际CSS.supports为false，computed背景为不透明rgb(246,250,255)；未覆盖/替换CSS或伪造DOM能力。Chrome另有可信原生浏览器组合输入；Firefox只验证原生协议Unicode插入与键盘，物理输入法未验。触屏为Windows仿真，不是真手机。


已有结果恢复和下载：两浏览器×两角色共4组，恢复D36已有会话的3家企业、原文件选择/移除、原下载按钮获取已有三表Excel，与持久file_hash一致并由实际openpyxl读取，再原生刷新同样结果。不新建会话、查询、上传或导出任务，原下载审计照常追加。Firefox product在依赖检查脚本失败前已下载，后续复用原文件不重复下载；工作簿组件使用已有company-test解释器，不安装包。


本地恢复范围：完整捕获两业务数据库，原私有附件/导出、现存来源正文/研究收据、源表副本、当前应用源码、必要账号/密钥及模型配置。私有目录由当前Windows SID控制，文档只引用路径/哈希，不输出密钥。18451个文件共1131103415字节逐项原件→捕获→恢复核对；两库在捕获及回读间保持稳定。恢复副本portal93表/platform6表结构及完整表摘要、integrity_check和外键通过；应用从恢复目录导入，实际两套密码/绑定检查、自己的会话/快照、对方快照拒绝、既有Excel读取与对方下载拒绝、36份附件哈希通过。副本仅读取验收产生审计追加，旧审计完整保留。禁止读取原运行数据、阻止出站和模型；仅许可已加载验证脚本源码供traceback读行。urllib3导入时一次本地bind能力探测被阻止并单独记录，不当作外网调用。


恢复边界：此次是同机现有解释器依赖下的全量本地业务资料恢复和应用回读。没有OS镜像/新机器冷安装、跨库原子事务、主库恢复、实际切换或模型API可用性验收；检查双库在捕获区间未变更。中间维护SQLite历史备份不纳入运行恢复包，当前运行库和非SQL研究证据保存。历史已缺的一份HTML未凭空恢复，原解析正文和原哈希证据继续保留。版本绑定及D38被测87输入源码包位于release-binding，原测试源码未变，本轮不重跑617/16或相加计数。


保留的失败：原Firefox默认缓存启动缺mozglue程序集；只在完整隔离副本补原mozglue.dll资源提取的清单，exe/dll字节不改，不动系统或原浏览器。无blur首检查误将computed缺属性None判失败；Chrome首脚本提前关闭context；文件首脚本误期望原生input保留files（组件正常清空以便重选）；随后工作簿检查误用无openpyxl的浏览器解释器。以上原FAIL都保留，修正验证程序后当前完整用例通过，没有修改应用迁就测试。完整恢复首守卫把本地bind探测和本验证脚本traceback源读取误作外网/原资料读取，原FAIL及诊断保存；修正分类后原资料仍严格禁止。Chrome首次慢传及一次连接重置失败保留，分段有限恢复只补未完成片段，完整ZIP CRC/大小及SHA核对。


公开实现与许可：Chrome获取方式依据[Chrome for Testing官方说明](https://github.com/GoogleChromeLabs/chrome-for-testing)及固定下载索引；实际155.0.8059.84/win64，压缩包206114888字节，SHA507f2a031441d10c62b5e3d4e863f09ac1198a571c1419976cbd8387f639afde。浏览器受Google Chrome二进制条款约束，仓库说明代码Apache-2.0不能替代浏览器许可；仅测试工具，不纳入产品源码。Firefox来自既有官方Playwright1555发行包，浏览器MPL-2.0及原第三方许可保留、Playwright工具Apache-2.0；依据[Playwright浏览器文档](https://playwright.dev/docs/browsers)。应用本地程序集布局依据[Microsoft私有程序集文档](https://learn.microsoft.com/en-us/windows/win32/sbscs/about-private-assemblies-)；只复用原清单，不导入微软实现代码。Chrome程序Authenticode返回NotSigned，记录真实结果，不宣称验签通过；来源为官方HTTPS版本地址及完整包哈希，不修改签名或系统策略。


- 私有证据 `.runtime/baichuan-ai-local/night-acceptance-20261018/d39-predeployment-completion/compat-firefox/receipt.json`；SHA256 `45a87e8cb793a9aa07fb27c9b75314c6b9c6aa9b17eb1177fe659f891cd23bc4`。


- 私有证据 `.runtime/baichuan-ai-local/night-acceptance-20261018/d39-predeployment-completion/compat-firefox-no-blur-final/receipt.json`；SHA256 `d3e06a8ff0c7ebed7505c325fa57375f02b49f3b23acc2ccc6c38337cac09168`。


- 私有证据 `.runtime/baichuan-ai-local/night-acceptance-20261018/d39-predeployment-completion/compat-chrome-complete/receipt.json`；SHA256 `3dfe34e37bd373cc274cff167fac9909230d61081e382b411a49df383d477476`。


- 私有证据 `.runtime/baichuan-ai-local/night-acceptance-20261018/d39-predeployment-completion/result-download-firefox-final/receipt.json`；SHA256 `1face0822e36d518d61a96c0428cff9a8c09d3640769a263a57afd71e58cfd95`。


- 私有证据 `.runtime/baichuan-ai-local/night-acceptance-20261018/d39-predeployment-completion/result-download-chrome-final/receipt.json`；SHA256 `fc2f0bafbe0cbae8eefd20db96a76527b6438ca53706a06303e257b345af9aa4`。


- 私有证据 `.runtime/baichuan-ai-local/night-acceptance-20261018/d39-predeployment-completion/full-restore/final-receipt.json`；SHA256 `86bf41df8c8fb59f37a98c44d6bf568b5bd7d5b04f38ce32416026ba1ee2993b`。


- 私有证据 `.runtime/baichuan-ai-local/night-acceptance-20261018/d39-predeployment-completion/full-restore/application-readback-final.json`；SHA256 `0cf25dd0bf98c3f3620adc1ab00e98a3ff5f4ad49621e3518b4584ea1b0a4c09`。


- 私有证据 `.runtime/baichuan-ai-local/night-acceptance-20261018/d39-predeployment-completion/browsers/chrome-range-resume/receipt.json`；SHA256 `48902eb1c8432d06827d670d2acbeea27bb7f05ac007935be9242e0c44d2588a`。


最终保护核账 `.runtime/baichuan-ai-local/night-acceptance-20261018/d39-predeployment-completion/closure.json`，SHA256 `f34c897cc796c62e9333e8304efa172914255bd13a490ab11bad50484c037d7d`。

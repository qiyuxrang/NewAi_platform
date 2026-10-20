# AI-T05：证书归并修复、最终回归与所属后端加载

实际完整回归：2026-10-18 03:55:13–03:58:41（北京时间）。27个模块、360项测试全部通过，198.526秒，0跳过；54个业务/测试/执行入口SHA前后一致并由根代理复查。此前343项、70专项与本轮重叠，不相加。原14项9FAIL/5PASS日志保留；修复后新增3个保护用例，17专项纳入本轮。

跨企业证据scope的证书不参与本scope去重或冲突。无证据人工旧声明继续受保护。同号重放需全部声明字段、已核实状态、当前scope有效来源、已应用证书修订绑定均一致；issuer、standard、范围、主体或状态变化不能提前返回旧修订。同scope同号差异仍冲突，不增加同等级旧声明豁免，也不放宽有效起始、主体或来源要求。

03:59:26.675232仅所属portal26572/worker13868完成实际加载，改变业务文件只有baichuan_facts.py。在线备份quick_check=ok，加载前后13张业务/权限/旧会话快照表完整摘要和数量一致、Model26不变、无在途任务，4health均200/5进程owned。前端PID21632及163指纹、两个网关、源Excel/旧试运行库保持。0seed/迁移/模型/前端构建/前端重启；远程未操作。

- 核心SHA：`7e3783ba697b060379323d63472652bb52cf77f7e6c15dfa7dd5b579030f56c8`
- 回归receipt SHA：`788d8f06337de9e96afe3a86bb5ab366872fdbee3cb2cb3c0598adc40c75f581`
- 回归log SHA：`8174f5e777323110b4963941507524186c6c0d4f9c462ef6e7312e56bda90f97`
- 加载receipt SHA：`d34e75b19fde40b56297ff5b302675a7506edf14d9c8f6774b7e33a15d54c01d`

私有证据在 `.runtime/baichuan-ai-local/night-acceptance-20261018/certificate-reconciliation-final-regression/` 及 `certificate-reconciliation-owned-backend-load/`。旧[复现证据](2026-10-18-certificate-reconciliation-reproduction.md)保留失败与窄修范围。AI-T05实现恢复DONE；360项不代表全部UI/全库研究验收通过。原断网验收器FAIL和同context重连未执行仍保留，新v2另按本加载版本独立验收；ITSS获证/发证日仍不推有效起始，真实证书核实0。

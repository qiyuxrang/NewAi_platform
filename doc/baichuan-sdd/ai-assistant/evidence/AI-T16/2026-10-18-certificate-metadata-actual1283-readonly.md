# AI-T16：证号元数据修复后的实际1283只读匹配

实际执行UTC 2026-10-17T19:19:22.265595+00:00 至 2026-10-17T19:19:31.779759+00:00（北京时间03:19:22–03:19:31）。新独立脚本读取既有合法条件快照，匹配器为新源码5ca981f3…01d6；旧性能样本保持原时点，现有服务尚未加载本次修复。

固定实际原表1283家，1连接首轮518.862ms；12热样本nearest-rank P95 700.732ms，低于本单元2000ms目标。13轮均返回1283候选/0确认、663个绑定本企业/类别/来源的冻结证书元数据；未核实结论不变，各轮结果SHA一致，每轮24条SELECT。

真实URI mode=ro、query_only和ORM SELECT单语句守卫；禁止socket/DNS。94表逐行摘要前后相等，模型日志25→25、163前端SHA保持。HTTP/模型/业务写入/新快照/服务操作均0。不是HTTP全链路、页面绘制、模型延时、XLSX或总体P95，也未清OS缓存。

私有`.runtime/baichuan-ai-local/night-acceptance-20261018/actual-catalog-match-certificates-ro/receipt.json` SHA256 `0843f9b0e9add443ac3032fdd478b05ef7fdb59e966382c600445ed449fed886`，保存13轮逐样本、全部94表前后摘要与运行环境；新脚本actual-catalog-match-certificates-ro.py保留，不修改原actual-catalog-match-ro样本。

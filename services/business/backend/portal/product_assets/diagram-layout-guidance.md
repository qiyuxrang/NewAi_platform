# 报告图形语义与布局适配

先按正文关系选择表达方式，再绘图：
- 分层架构：用 flowchart TB 的 subgraph 表示正文已有的层级，每层只放该层组件；跨层连线表示调用或数据流，不能把所有组件排成业务流水线。
- 网络、部署、范围边界：用嵌套 subgraph 表示正文已有的环境或区域；只连接正文明确支持的设备或组件，不新增网段、厂商、实例或数量。
- 业务活动与决策：用 flowchart TB 表示动作；只有正文提供条件时才用菱形，至少两个去向并分别标明条件，回退线回到实际返修步骤。正文没有分支时不制造“是/否”。
- 多角色按时间交互：用 sequenceDiagram，参与者采用业务名称，消息用短动词；正文存在替代条件才使用 alt/else，存在重复才使用 loop。不要把静态架构画成时序。
- 数据加工或交付流水线：短链可用 flowchart LR，超过四个连续阶段优先 TB；同层并列组件可分组，避免超宽横图和逐节点跨页。

每图只表达一个完整机制，通常三至八节点；正文只支持两个实体时允许双节点关系图。节点写短名称或动作，建议四至十四个汉字；限定词保留在相关节点或关系上。说明文字留在图说明中，不把整段正文塞入节点。禁止单节点摘录卡、占位节点和没有关系的节点堆砌进入正常完成状态。版面保持最大145mm宽、190mm阅读单元、最小10.5pt；无法兼顾时应返回可定位问题供有界修正，不以缩小文字解决。

## 来源与使用边界

- 参考仓库：https://github.com/Julylovin/xicilion-skills
- 固定版本：ba6c97621ef44764eb1d862890e7e516b8f4860f（2026-10-15读取）
- 参考资源：architecture/SKILL.md、architecture/layouts/single-stack.md、architecture/layouts/nested-containers.md、uml/SKILL.md、uml/examples/activity-diagram.md、uml/examples/sequence-diagram.md、network/SKILL.md、graphviz/SKILL.md。
- 实际适配：复用分类决策、纵向层级、容器边界、活动分支与时序条件的设计方法，以原创中文规则映射到现有受控 Mermaid 生成与检查链；本文件参与提示词和图形契约哈希。
- 许可证：读取时仓库未提供许可证文件，GitHub API 的 license 为 null。未复制或分发上游模板、代码、图标与样式；若以后引入这些资产，须先确认使用许可。
- 当前只支持 Mermaid flowchart 与 sequenceDiagram；未安装或声明 PlantUML、Graphviz、上游 HTML 架构渲染能力。Word字号、颜色、图题位置与页面格式仍使用现有契约。

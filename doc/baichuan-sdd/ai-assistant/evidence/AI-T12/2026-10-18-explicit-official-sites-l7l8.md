# AI-T12：L7/L8 两条显式官网线索补证

2026-10-18 02:19（+08:00）。固定两个已有目录明确披露的原HTTP官网，不猜协议/域名/路径、不新搜索、0模型/业务写入/前端/服务操作。每家最多2页，实际未取得任何新官网正文；0安全候选，未创建可应用批次。

| 主体及实际只读版本 | 显式线索与本轮实际 |
| --- | --- |
| 陕西万德信息科技股份有限公司，9bd6dae8-c071-5f8c-9a75-c1f2486e0fe2 / v3 | 已保存 [企业目录](https://www.maigoo.com/company/46246.html) 正文明示 http://www.sxwdsoft.com/。现官网/邮箱为空，地址/city已由根补入。已有 o-direct-fetch/research-o/L7 对同域 HTTPS 失败记录；按本轮不重试失败domain限制跳过，0新HTTP。不能因目录声称官网即写website。 |
| 陕西建工集团数字科技有限公司，e158d3f2-5767-5621-92b7-486b94e9a24c / v3 | 已保存 [CMMI目录](https://www.cmmizw.com/Company_40562.html) 可见“官网：www.sjcloud.com.cn”与精确 href=http://www.sjcloud.com.cn/，完整主体含“集团”。现仅官网为空，根已补地址/邮箱保留。对原HTTP根URL做1次有界访问意图，public DNS前置检查即 gaierror11001；尚未发送HTTP GET，正文/响应0，无可见同源导航可继续。未升级HTTPS、未重试。 |

该单元新URL尝试1、发送HTTP GET0、响应/新正文0；另1家按失败domain限制跳过。没有查看官网主体/版权/业务电话的正文依据，因此当前官网归属仍未知；目录披露不是主管机关/发证核验，资质不升级。

最初离线准备只允许完整URL出现在纯文字，L8可见正文省略scheme但原HTML真实anchor保留完整HTTP，因此准备阶段停止，0请求。另存 explicit-sites-l7l8-prepare-first-failure.json 后只放行精确原HTML href，并记录raw/body hash；没有猜测scheme。随后DNS失败原件和读取阶段journal副本均保留。

私有 independent-enrichment-20261017/ 新文件：cohort-explicit-sites-l7l8.json、research-explicit-sites-l7l8.json、explicit-sites-l7l8-read-phase-original.json、explicit-sites-l7l8-final-receipt.json、explicit-sites-l7l8-raw/唯一intent。没有伪造raw/body文件；原L7/L8日志/批次均不修改，最终收据保留它们的SHA。

冻结 journal SHA256 `720439ef89c4479c0bde81bcc542f2284d6945a2f9c3736d06c1b651b3b6cdc7`，最终 receipt SHA256 `b057a244089275f89990fe2446e30f573d0270d8bb60f2d654dd4a02eebbb8e5`。

仅完成这两条线索的有界补证及缺口记录，不计新增企业发现、不计资料核实或补空。恢复需外部访问状态变化或新的明确失败域名重试范围，本单元结束，不自动重试。

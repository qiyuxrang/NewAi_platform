# AI-T04 / AI-T07 / AI-T08 首个隔离验证单元

日期：2026-10-17；环境：新建隔离 Django 测试库，未读取或写入用户企业库。HEAD ef1676cd8327d693dab897c45a234ba91413884e + 当前工作区。

实现：baichuan_conditions.py 有界白名单条件树、四态逻辑；baichuan_matching.py 结构化确定性匹配与不可变结果；assistant_service/api/worker 对话、附件、持久任务编排。新增解释器隔离入口 scripts/baichuan/check_backend.py，去除所有继承 PORTAL 配置，创建临时库/私有存储。

执行：`.runtime/company-test/python/Scripts/python.exe scripts/baichuan/check_backend.py portal.tests.test_baichuan_conditions portal.tests.test_baichuan_assistant`。实际结果：16 tests，8.623 秒，OK。初轮接口测试发现 SimpleLazyObject 不能用 type(user).objects；改为 get_user_model() 后重跑全部上述检查通过。

覆盖：AND/OR/NOT、深度/数量限制、SQL/ORM字段拒绝、等级方向不同的虚构版本规则、缺主体/日期/撤销状态/正文依据保留候选、非完整证书清单不推定不存在、硬条件失败不被优先项抵消；消息幂等、不同内容409、条件版本冲突、他人/跨部署对象404、附件格式与危险ZIP、模型缺能力失败、伪造条款引用拒绝、过时轮次隔离、快照读取权限与功能开关。

局限：测试模型响应采用明确fixture，不能作为真实模型网关可用证据；生产类别字典/完整来源版本仍在建立，联网编排待联调；文件真实解析能力另见AI-T02，上传与任务联动未完成全链路浏览器验收。AI-T04/07/08保持IN_PROGRESS，不宣告整体验收通过。

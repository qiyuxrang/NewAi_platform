# 本机联网搜索

知识助手和产品三件套共用 `portal/product_web_search.py`。SearXNG 由企业 Compose 管理，固定官方镜像摘要，仅监听 `127.0.0.1:19881`。

启动：`powershell -File scripts/start-search.ps1`。企业启动脚本也会启动搜索服务；企业完整停止时保留容器和配置。

在 `services/business/.runtime/local.env` 中配置后，重启 portal 和空闲的 product worker：

```dotenv
PORTAL_PRODUCT_WEB_SEARCH_ENABLED=1
PORTAL_PRODUCT_WEB_SEARCH_PROVIDER=searxng
PORTAL_PRODUCT_WEB_SEARCH_SEARXNG_URL=http://127.0.0.1:19881
```

首次启动自动生成 `.runtime/search/settings.yml` 和随机 secret，后续保留配置。当前启用搜狗、360，已验证本机中文技术查询；无需搜索 API 密钥。上游可能限流、验证码或超时，服务启动成功不保证每次搜索有结果。

健康检查：`http://127.0.0.1:19881/healthz`。真实查询：`http://127.0.0.1:19881/search?q=SearXNG&format=json`。日志：`docker compose --env-file .env -f docker-compose.enterprise.yml logs --tail 50 searxng`。

助手默认关闭联网，用户开启后仅发送本次问题；历史与知识库正文不作外网查询。界面展示实际检索步骤与来源，最终回答流式输出。

三件套先检索已授权知识库，技术覆盖不足时仅以固定技术分类联网补充。公开结果保留 URL、检索时间和 `PUBLIC_REFERENCE/UNKNOWN` 标记，蓝图人工确认、版本及发布授权继续有效。

代码回归（使用隔离测试配置/测试数据库）：`python manage.py test portal.tests.test_product_knowledge_agent portal.tests.test_product_knowledge_api portal.tests.test_product_web_search portal.tests.test_product_blueprint_retrieval portal.tests.test_product_required_knowledge --noinput`。

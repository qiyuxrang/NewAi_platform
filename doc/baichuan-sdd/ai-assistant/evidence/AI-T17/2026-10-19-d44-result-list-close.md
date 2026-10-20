# AI-D44 企业结果列表关闭按钮

用户要求：为截图所示助手企业结果面板添加关闭按钮。

## 实现

- `frontend/src/business/product/BaichuanAssistant.tsx`：复用原收起结果列表状态，显示X/关闭和可访问名称，关闭后恢复入口焦点。
- `frontend/src/business/product/BaichuanAssistant.css`：原标题栏CSS sticky，关闭按钮在列表滚动后仍可见。
- `frontend/tests/baichuan-assistant.test.mjs`：原固定快照行为测试增加关闭后会话保留及助手恢复断言。

## 实际检查

- `node --test tests/baichuan-assistant.test.mjs`：16通过，0失败/跳过。
- 助手文件ESLint、`tsc -b`、`vite build`：通过；构建保留既有大包体积提示。
- 当前3080真实Chrome、正常总经理账号、原有50家快照：1920×1080及1440×900，两组均通过滚动到底按钮视口/点击命中、关闭及焦点恢复、重新打开同一会话/首家公司、Enter关闭；0助手写请求、0页面错误。
- 产品事业部和总经理复用本次修改的同一组件；产品账号浏览器本轮未单独验收。无后端修改，未运行后端测试。
- 原始脚本/收据/截图：`.runtime/enterprise/assistant-close-20261019/verify-close.py`、`result.json`、`manager_user-1920-scrolled.png`、`manager_user-1440-scrolled.png`。只恢复历史结果，未发送新查询、创建任务、写企业资料或重启服务。

只完成本次按钮需求，不据此扩大既有SDD验收范围。保留所有其他工作区改动，未提交或推送GitHub。

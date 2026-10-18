// Local isolation marker is injected by the dev server, never into production builds.
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../frontend');
const defaultLabel = '隔离开发库，尚未连接现有企业资料';
const sourceLabel = '本地源表资料，历史官网补查未恢复';
// Only fixed plain labels enter HTML; source metadata is never rendered as HTML.
const environmentLabel = process.env.PORTAL_BAICHUAN_ENVIRONMENT_LABEL === sourceLabel ? sourceLabel : defaultLabel;
const { createServer, loadConfigFromFile } = await import(pathToFileURL(path.join(root, 'node_modules/vite/dist/node/index.js')).href);
const loaded = await loadConfigFromFile({ command: 'serve', mode: 'development' }, path.join(root, 'vite.config.ts'));
const server = await createServer({ ...loaded.config, root, configFile: false,
  plugins: [...loaded.config.plugins, { name: 'baichuan-local-isolation', transformIndexHtml() {
    return [{ tag: 'div', attrs: { role: 'status', id: 'baichuan-local-environment',
      style: 'position:fixed;bottom:0;left:0;right:0;z-index:2147483647;background:#fff2b8;color:#512f00;font:14px/24px sans-serif;text-align:center;pointer-events:none;' },
      children: environmentLabel, injectTo: 'body' }];
  } }],
  server: { ...loaded.config.server, host: '127.0.0.1', port: 13180, strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:18080' } } });
await server.listen();
server.printUrls();

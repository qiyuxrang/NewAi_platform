// Serve the existing frontend with a trial-only API target; no response fixtures.
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'frontend');
const { createServer, loadConfigFromFile } = await import(pathToFileURL(path.join(root, 'node_modules/vite/dist/node/index.js')).href);
const loaded = await loadConfigFromFile({ command: 'serve', mode: 'development' }, path.join(root, 'vite.config.ts'));
const server = await createServer({ ...loaded.config, root, configFile: false,
  server: { ...loaded.config.server, host: '127.0.0.1', port: 13180, strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:18080' } } });
await server.listen();
server.printUrls();

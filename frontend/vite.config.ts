import { existsSync } from 'node:fs';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

/** 开发期把 /admin 下的深链回退到 admin/index.html。
 *  Vite 的 SPA 回退只认根 index.html，多入口时会把 /admin/sessions 错给客户端页面；
 *  生产由编排服务的 /admin/{path} 路由负责（见 orchestrator/app/main.py）。 */
const adminSpaFallback = {
  name: 'admin-spa-fallback',
  configureServer(server: { middlewares: { use: (fn: (req: { url?: string }, res: unknown, next: () => void) => void) => void } }) {
    server.middlewares.use((req, _res, next) => {
      const path = (req.url ?? '').split('?')[0] ?? '';
      if (path.startsWith('/admin') && !path.startsWith('/admin/api') && !/\.[a-z]+$/i.test(path)) {
        req.url = '/admin/index.html';
      }
      next();
    });
  },
};

const entry = (name: string): string => {
  const path = new URL(name, import.meta.url).pathname;
  // 构建镜像时漏拷 admin/ 会让 Vite 静默少打一个入口，线上 /admin 直接 404。宁可构建失败。
  if (!existsSync(path)) throw new Error(`缺少构建入口 ${name}（检查 Dockerfile 的 COPY）`);
  return path;
};

export default defineConfig({
  plugins: [react(), adminSpaFallback],
  build: {
    // 两个入口：客户聊天（index）与管理员观测台（admin）。分开打包，聊天端不引入图表 / 图库。
    rollupOptions: {
      input: {
        index: entry('index.html'),
        admin: entry('admin/index.html'),
      },
    },
  },
  server: {
    // 开发时仍请求同源 /health；生产构建由 FastAPI 直接托管。
    proxy: {
      '/health': 'http://127.0.0.1:8000',
      '/sessions': 'http://127.0.0.1:8000',
      '/models': 'http://127.0.0.1:8000',
      '/admin/api': 'http://127.0.0.1:8000',
    },
  },
});

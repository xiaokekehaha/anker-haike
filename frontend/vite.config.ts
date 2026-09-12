import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  server: {
    // 开发时仍请求同源 /health；生产构建由 FastAPI 直接托管。
    proxy: { '/health': 'http://127.0.0.1:8000' },
  },
});

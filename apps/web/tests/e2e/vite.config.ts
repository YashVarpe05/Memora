import { defineConfig, mergeConfig } from 'vite';
import base from '../../vite.config';

export default mergeConfig(base, defineConfig({
  cacheDir: 'node_modules/.vite-e2e',
  server: {
    host: '127.0.0.1', port: Number(process.env.MEMORA_E2E_WEB_PORT || 18173), strictPort: true,
    watch: { ignored: ['**/android/**', '**/test-results/**', '**/playwright-report/**'] },
    proxy: { '/api': {
      target: `http://127.0.0.1:${process.env.MEMORA_E2E_API_PORT || 18080}`,
      changeOrigin: true, rewrite: (path: string) => path.replace(/^\/api/, ''),
    } },
  },
}));

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The API serves the built dashboard under /app/. In dev, API paths are proxied to uvicorn.
const api = 'http://127.0.0.1:8000'
const paths = [
  'task', 'feedback', 'proposals', 'gate', 'patches', 'versions', 'rollback', 'audit',
  'overview', 'kb', 'tasks', 'trust', 'explain', 'passport', 'demo', 'queue', 'eval', 'health',
]

export default defineConfig({
  base: '/app/',
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { [`^/(${paths.join('|')})(/.*)?$`]: { target: api, changeOrigin: true } },
  },
  build: { outDir: 'dist', sourcemap: false, chunkSizeWarningLimit: 900 },
})

import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const proxy = {
  '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
}
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy,
    fs: {
      allow: [fileURLToPath(new URL('..', import.meta.url))],
      deny: ['.env', '.env.*', '**/.git/**', '**/backend/**'],
    },
  },
  preview: { host: '127.0.0.1', port: 4173, strictPort: true, proxy },
})

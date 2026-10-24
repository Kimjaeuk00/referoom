import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  // 백엔드 CORS 허용 Origin(http://localhost:5174)과 맞추기 위해 포트를 고정한다
  server: { port: 5174, strictPort: true },
  preview: { port: 5174, strictPort: true },
})

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发期把 /api 代理给 FastAPI(localhost:8000),这样前端 fetch('/api/...') 是同源请求,
// 免去跨域问题,也不用在代码里写死后端地址。
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 用 127.0.0.1 而非 localhost: Windows 上 localhost 可能解析到 IPv6(::1),
      // 而后端默认绑 IPv4(127.0.0.1),会导致代理连不上。
      '/api': 'http://127.0.0.1:8000',
    },
  },
})

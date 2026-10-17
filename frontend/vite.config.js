import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        // Usa 127.0.0.1 explícito — no Windows, "localhost" pode resolver
        // para IPv6 (::1) enquanto o uvicorn escuta apenas em IPv4.
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
        ws: true, // necessário para SSE / WebSocket
        configure: (proxy) => {
          proxy.on('error', (err, _req, res) => {
            console.error('\n[Vite Proxy] Backend indisponível:', err.message)
            console.error('  → Certifique-se de que o backend está rodando:')
            console.error('  → cd backend && python -m uvicorn main:app --reload --port 8000\n')
            // Responde com JSON de erro em vez de deixar o browser travar
            if (res && !res.headersSent) {
              res.writeHead(503, { 'Content-Type': 'application/json' })
              res.end(JSON.stringify({ detail: 'Backend offline', ollama: false, models: [] }))
            }
          })
          proxy.on('proxyReq', (_proxyReq, req) => {
            if (process.env.VITE_LOG_PROXY) {
              console.log('[Proxy]', req.method, req.url)
            }
          })
        },
      },
    },
  },
})

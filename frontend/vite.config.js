import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { viteStaticCopy } from 'vite-plugin-static-copy'

// Modelo Silero VAD, worklet de áudio e runtime ONNX servidos localmente em /vad (funciona offline)
const vadAssets = viteStaticCopy({
  targets: [
    { src: 'node_modules/@ricky0123/vad-web/dist/vad.worklet.bundle.min.js', dest: 'vad' },
    { src: 'node_modules/@ricky0123/vad-web/dist/silero_vad_v5.onnx', dest: 'vad' },
    { src: 'node_modules/onnxruntime-web/dist/*.wasm', dest: 'vad' },
    { src: 'node_modules/onnxruntime-web/dist/*.mjs', dest: 'vad' },
  ],
})

export default defineConfig({
  plugins: [react(), vadAssets],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        // Usa 127.0.0.1 explícito — no Windows, "localhost" pode resolver
        // para IPv6 (::1) enquanto o uvicorn escuta apenas em IPv4.
        target: `http://127.0.0.1:${process.env.BACKEND_PORT ?? 8010}`,
        changeOrigin: true,
        secure: false,
        ws: true, // necessário para SSE / WebSocket
        configure: (proxy) => {
          proxy.on('error', (err, _req, res) => {
            console.error('\n[Vite Proxy] Backend indisponível:', err.message)
            console.error('  → Certifique-se de que o backend está rodando:')
            console.error('  → cd backend && python -m uvicorn main:app --reload --port 8010\n')
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

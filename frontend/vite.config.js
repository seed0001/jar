import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/chat':     { target: 'http://localhost:8765', changeOrigin: true },
      '/health':   { target: 'http://localhost:8765', changeOrigin: true },
      '/sessions': { target: 'http://localhost:8765', changeOrigin: true },
      '/voice':    { target: 'http://localhost:8765', changeOrigin: true },
      '/skills':   { target: 'http://localhost:8765', changeOrigin: true },
      '/skillbank':{ target: 'http://localhost:8765', changeOrigin: true },
      '/greeting': { target: 'http://localhost:8765', changeOrigin: true },
      '/memory':   { target: 'http://localhost:8765', changeOrigin: true },
      '/feedback': { target: 'http://localhost:8765', changeOrigin: true },
      '/schema':   { target: 'http://localhost:8765', changeOrigin: true },
      '/profile':  { target: 'http://localhost:8765', changeOrigin: true },
      '/models':   { target: 'http://localhost:8765', changeOrigin: true },
    }
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  }
})

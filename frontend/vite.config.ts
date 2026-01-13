import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      port: 3000,
      proxy: {
        '/api': {
          target: env.VITE_API_URL || 'http://localhost:8000',
          changeOrigin: true,
          ws: true,  // Enable WebSocket proxy for chat
        },
      },
    },
    // Production build settings
    build: {
      outDir: 'dist',
      sourcemap: false,
      // Inline small assets
      assetsInlineLimit: 4096,
    },
    // Note: API_KEY is NOT included in client bundle (security)
    // API authentication is handled by nginx proxy injection
  }
})

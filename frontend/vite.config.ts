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
    // Define environment variables for client-side
    define: {
      // Make API key available at build time (for production builds)
      __API_KEY__: JSON.stringify(env.VITE_API_KEY || ''),
    },
  }
})

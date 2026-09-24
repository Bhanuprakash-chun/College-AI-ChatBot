import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backend = env.VITE_BACKEND_URL || 'http://127.0.0.1:8001'

  return {
    plugins: [react(), tailwindcss()],

    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes('node_modules')) return undefined

            if (
              /react-markdown|remark|mdast|micromark|unified|hast|unist|vfile|property-information/.test(id)
            ) {
              return 'markdown'
            }

            if (
              /react-router|react-dom|node_modules\/react\/|scheduler/.test(id)
            ) {
              return 'react'
            }

            if (id.includes('lucide-react')) {
              return 'icons'
            }

            return 'vendor'
          },
        },
      },
    },

    server: {
      port: 5173,
      strictPort: true,

      allowedHosts: [
        'opens-waves-morrison-syracuse.trycloudflare.com',
      ],

      proxy: {
        '/api': {
          target: backend,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
      },
    },

    preview: {
      port: 4173,

      proxy: {
        '/api': {
          target: backend,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
      },
    },
  }
})
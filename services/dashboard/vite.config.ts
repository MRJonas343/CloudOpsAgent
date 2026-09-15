import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

/**
 * Same-origin API paths, exactly as nginx serves them in the container: the
 * browser calls `/api/agent/*` and `/api/app/*` and never crosses an origin.
 * The dev server and the preview server mirror those paths onto the local
 * backends so `npm run dev` exercises the same contract as the Docker build.
 */
const proxy = {
  '/api/agent': {
    target: 'http://localhost:8000',
    changeOrigin: true,
    rewrite: (path: string) => path.replace(/^\/api\/agent/, ''),
  },
  '/api/app': {
    target: 'http://localhost:8001',
    changeOrigin: true,
    rewrite: (path: string) => path.replace(/^\/api\/app/, ''),
  },
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, proxy },
  preview: { port: 3000, proxy },
})

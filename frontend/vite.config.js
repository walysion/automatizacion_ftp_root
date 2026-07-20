import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: true,
    proxy: {
      '/api': {
        target: 'http://app:5000', // Apunta al contenedor de Flask internamente
        changeOrigin: true
      }
    }
  }
})
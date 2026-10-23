import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import {readFileSync} from 'node:fs'
const version=JSON.parse(readFileSync(new URL('./package.json',import.meta.url),'utf8')).version

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(),{name:'app-version',generateBundle(){this.emitFile({type:'asset',fileName:'app-version.json',source:JSON.stringify({version})})}}],
  server: { host: '127.0.0.1', port: 5173, strictPort: true, proxy: { '/api': 'http://127.0.0.1:8765' } },
})

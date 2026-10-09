import react, { reactCompilerPreset } from '@vitejs/plugin-react'
import babel from '@rolldown/plugin-babel'
import { defineConfig, loadEnv } from 'vite'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
// `--mode api` points the workspace at a local BioVerdict API unless VITE_API_URL says otherwise.
// Without either, the build opens the prepared snapshot and makes no network calls.
const LOCAL_API = 'http://127.0.0.1:8000'

export default defineConfig(({ mode }) => {
  const configured = loadEnv(mode, import.meta.dirname, 'VITE_').VITE_API_URL
  return {
    plugins: [tailwindcss(), react(), babel({ presets: [reactCompilerPreset()] })],
    define:
      mode === 'api' && !configured
        ? { 'import.meta.env.VITE_API_URL': JSON.stringify(LOCAL_API) }
        : {},
  }
})

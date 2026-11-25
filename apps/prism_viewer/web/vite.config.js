import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"
import Components from "unplugin-vue-components/vite"
import { ElementPlusResolver } from "unplugin-vue-components/resolvers"
import UnoCSS from "unocss/vite"
import { fileURLToPath, URL } from "node:url"

// The viewer's server the dev server proxies to; PRISM_VIEWER_API names another.
const apiTarget = process.env.PRISM_VIEWER_API || "http://127.0.0.1:8790"

export default defineConfig({
  base: "./",
  plugins: [
    vue(),
    UnoCSS(),
    Components({
      dirs: [],
      resolvers: [ElementPlusResolver()],
    }),
  ],
  resolve: {
    alias: [{ find: "@", replacement: fileURLToPath(new URL("./src", import.meta.url)) }],
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": { target: apiTarget, changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    chunkSizeWarningLimit: 1200,
  },
})

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

// Бұл жоба SPA ЕМЕС — index.html тек `npm run dev` кезінде сынау үшін
// қолданылады. Production build `src/main.tsx`-ты тікелей JS кіру нүктесі
// ретінде алады да, FastAPI static серверіне СӘЙКЕС аттармен (main.js/
// main.css, hash-сіз) шығарады — server/app/web/templates/base.html
// осыларды тұрақты жолмен <script>/<link> қылып қосады.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: {
      input: resolve(__dirname, "src/main.tsx"),
      output: {
        entryFileNames: "main.js",
        chunkFileNames: "chunk-[name].js",
        assetFileNames: (info) =>
          info.name && info.name.endsWith(".css") ? "main.css" : "[name][extname]",
      },
    },
  },
});

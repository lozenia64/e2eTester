import { defineConfig } from "vite";
import { resolve } from "node:path";

// Jinja 서버 렌더를 유지하는 다중 엔트리 빌드. SPA 아님.
// manifest 를 켜서 Jinja 가 해시 파일명을 해석한다(수동 ?v= 캐시버스팅 제거).
export default defineConfig({
  root: resolve(__dirname, "app/web/frontend"),
  build: {
    outDir: resolve(__dirname, "app/web/static/dist"),
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: {
        main: resolve(__dirname, "app/web/frontend/entries/main.ts"),
      },
    },
  },
  test: {
    environment: "jsdom",
    include: ["**/*.test.ts"],
  },
});

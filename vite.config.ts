import { defineConfig } from "vite";
import { resolve } from "node:path";

// Jinja 서버 렌더를 유지하는 다중 엔트리 빌드. SPA 아님.
// manifest 를 켜서 Jinja 가 해시 파일명을 해석한다(수동 ?v= 캐시버스팅 제거).
export default defineConfig({
  root: resolve(__dirname, "app/web/frontend"),
  // dist 는 app/main.py 의 `app.mount("/static", ...)` 아래 /static/dist 로 서빙된다.
  // CSS 안의 url(...)(폰트 92개 등)은 manifest 를 거치지 않고 이 base 로 직접
  // 해석되므로, 기본값 "/" 로 두면 /assets/*.woff2 를 찾다 전부 404 난다.
  base: "/static/dist/",
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

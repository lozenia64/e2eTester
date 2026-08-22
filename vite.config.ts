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
        // 상황판은 사이드바·Alpine·컴포넌트 TS 가 필요 없는 독립 화면이라
        // 별 엔트리로 둔다 — 일반 페이지 번들에 상황판 CSS 를 얹지 않기 위함.
        wall: resolve(__dirname, "app/web/frontend/entries/wall.ts"),
        // 차트 라이브러리 self-host(P3-4 §3.1). 레거시 페이지 스크립트가
        // 전역으로 쓰므로 브리지 엔트리로 얹는다 — 해당 화면이 P4 에서
        // 이관되는 시점에 이 세 줄과 엔트리 파일을 함께 지운다.
        "vendor-chart": resolve(__dirname, "app/web/frontend/entries/vendor-chart.ts"),
        "vendor-echarts": resolve(__dirname, "app/web/frontend/entries/vendor-echarts.ts"),
        "vendor-plotly": resolve(__dirname, "app/web/frontend/entries/vendor-plotly.ts"),
      },
    },
  },
  test: {
    environment: "jsdom",
    include: ["**/*.test.ts"],
  },
});

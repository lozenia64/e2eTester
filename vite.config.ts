import { defineConfig, type Plugin } from "vite";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// plotly.min.js 는 이미 minify 된 4.6MB UMD 다. 엔트리로 번들하면 Rollup 처리만으로
// 빌드 시간의 60%(약 12초)를 쓰고 얻는 것이 없어, 해시 자산으로 그대로 내보낸다.
// insights.js·admin-stats.js 가 전역 `Plotly` 를 쓰므로 템플릿이 일반 defer 스크립트로
// 먼저 싣는다. 두 파일이 P4 로 이관되면 이 플러그인을 지운다.
function emitPlotly(): Plugin {
  return {
    name: "emit-plotly",
    apply: "build",
    buildStart() {
      this.emitFile({
        type: "asset",
        name: "plotly.min.js",
        originalFileName: "vendor/plotly.min.js",
        source: readFileSync(resolve(__dirname, "node_modules/plotly.js-dist-min/plotly.min.js")),
      });
    },
  };
}

// Jinja 서버 렌더를 유지하는 다중 엔트리 빌드. SPA 아님.
// manifest 를 켜서 Jinja 가 해시 파일명을 해석한다(수동 ?v= 캐시버스팅 제거).
export default defineConfig({
  root: resolve(__dirname, "app/web/frontend"),
  plugins: [emitPlotly()],
  // dist 는 app/main.py 의 `app.mount("/static", ...)` 아래 /static/dist 로 서빙된다.
  // CSS 안의 url(...)(폰트 92개 등)은 manifest 를 거치지 않고 이 base 로 직접
  // 해석되므로, 기본값 "/" 로 두면 /assets/*.woff2 를 찾다 전부 404 난다.
  base: "/static/dist/",
  build: {
    outDir: resolve(__dirname, "app/web/static/dist"),
    // watch(`npm run dev`) 재빌드마다 dist 를 비우면, 그 순간 dist 를 읽는 pytest·Playwright 가
    // 깨진다. 파일명이 해시라 안 비워도 manifest 는 항상 새 파일만 가리킨다 — 비우기는 일회성
    // `vite build` 에서만 한다.
    emptyOutDir: !process.argv.includes("--watch"),
    manifest: true,
    rollupOptions: {
      input: {
        main: resolve(__dirname, "app/web/frontend/entries/main.ts"),
        // 상황판은 사이드바·Alpine·컴포넌트 TS 가 필요 없는 독립 화면이라
        // 별 엔트리로 둔다 — 일반 페이지 번들에 상황판 CSS 를 얹지 않기 위함.
        wall: resolve(__dirname, "app/web/frontend/entries/wall.ts"),
        dashboard: resolve(__dirname, "app/web/frontend/entries/dashboard.ts"),
        "admin-dashboard": resolve(__dirname, "app/web/frontend/entries/admin-dashboard.ts"),
        "admin-users": resolve(__dirname, "app/web/frontend/entries/admin-users.ts"),
        "admin-modules": resolve(__dirname, "app/web/frontend/entries/admin-modules.ts"),
        execute: resolve(__dirname, "app/web/frontend/entries/execute.ts"),
        suite: resolve(__dirname, "app/web/frontend/entries/suite.ts"),
        run: resolve(__dirname, "app/web/frontend/entries/run.ts"),
        "runs-history": resolve(__dirname, "app/web/frontend/entries/runs-history.ts"),
        // 차트 라이브러리 self-host(P3-4 §3.1). 레거시 페이지 스크립트가
        // 전역으로 쓰므로 브리지 엔트리로 얹는다 — 해당 화면이 P4 에서
        // 이관되는 시점에 이 줄과 엔트리 파일을 함께 지운다.
        "vendor-echarts": resolve(__dirname, "app/web/frontend/entries/vendor-echarts.ts"),
      },
    },
  },
  test: {
    environment: "jsdom",
    include: ["**/*.test.ts"],
  },
});

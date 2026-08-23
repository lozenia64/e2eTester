// 차트 라이브러리는 레거시 페이지 스크립트(app/web/static/*.js)가 전역으로 쓴다.
// 그 스크립트들을 고치지 않기 위한 과도기 선언이다(P3-4 §3.1).
// P4 가 admin-runs.js·insights.js·admin-stats.js 를 이관하면
// 이 파일과 entries/vendor-*.ts 를 함께 삭제한다.
export {};

type Htmx = typeof import("htmx.org").default;

declare global {
  interface Window {
    Chart: unknown;
    echarts: unknown;
    Plotly: unknown;
    htmx?: Htmx;
  }
}

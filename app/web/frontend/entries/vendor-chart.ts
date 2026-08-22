// 과도기 장치 — admin-runs.js 가 전역 `Chart` 를 쓴다(P3-4 §3.1).
// chart.js/auto 는 UMD 빌드와 동일하게 전 컨트롤러를 자동 등록한다.
// P4 가 admin-runs.js 를 이관하면 이 파일을 삭제한다.
import Chart from "chart.js/auto";

window.Chart = Chart;

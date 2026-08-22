// 과도기 장치 — admin-runs.js 가 전역 `echarts` 를 쓴다(P3-4 §3.1).
// P4 가 admin-runs.js 를 이관하면 이 파일을 삭제한다.
import * as echarts from "echarts";

window.echarts = echarts;

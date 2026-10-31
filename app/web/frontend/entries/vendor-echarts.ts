// 과도기 장치 — admin-runs.js 가 전역 `echarts` 를 쓴다(P3-4 §3.1).
// P4 가 admin-runs.js 를 이관하면 이 파일을 삭제한다.
// admin-runs.js 의 옵션에 새 series·component 를 쓰면 여기에도 등록한다.
// 빠지면 빌드는 통과하고 화면에서 그 요소만 조용히 사라진다.
// echarts/charts·components barrel 은 Rollup 이 전 모듈을 읽어 빌드가 느려지므로 쓰지 않는다.
import "echarts/lib/chart/heatmap";
import "echarts/lib/chart/treemap";
import "echarts/lib/component/grid";
import "echarts/lib/component/tooltip";
import "echarts/lib/component/visualMapPiecewise";
import { init, use } from "echarts/core";
import { LabelLayout, LegacyGridContainLabel } from "echarts/features";
import { CanvasRenderer } from "echarts/renderers";

// 전체 번들에서 옮겨오며 화면을 유지하는 기능들 — 빼면 heatmap 축 여백(containLabel)과
// 라벨 페이드인이 달라진다.
use([CanvasRenderer, LegacyGridContainLabel, LabelLayout]);

window.echarts = { init };

// charts.ts 가 지연 로드한다. echarts/charts·components barrel 은 Rollup 이 전 모듈을
// 읽어 빌드가 느려지므로, 쓰는 부품만 경로로 직접 등록한다.
import "echarts/lib/chart/line";
import "echarts/lib/component/grid";
import "echarts/lib/component/tooltip";
import { init, use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";

use(CanvasRenderer);

export { init };

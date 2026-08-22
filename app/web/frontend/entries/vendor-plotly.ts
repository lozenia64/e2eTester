// 과도기 장치 — insights.js·admin-stats.js 가 전역 `Plotly` 를 쓴다(P3-4 §3.1).
// 서버가 Python plotly.graph_objects 로 figure JSON 을 만들어 내려보내므로
// 라이브러리를 교체할 수 없다(설계 D1).
// P4 가 두 파일을 모두 이관하면 이 파일을 삭제한다.
import Plotly from "plotly.js-dist-min";

window.Plotly = Plotly;

// 어느 모듈에 초점을 둘 것인가 — Run 모듈 상태의 순수 함수(설계 §3.2·D4).
//
// 규칙의 소유자는 여기 하나뿐이다. 서버가 아니라 클라이언트가 갖는 이유는
// RunView.dump_from_summary 가 modules=[] 로 비우기 때문이다 — 초점이 바뀌는
// 계기(모듈 상태 변화)가 모듈 단위 이벤트로 오므로 서버는 snapshot 에서만
// 계산할 수 있고, 그러면 서버·클라이언트 두 벌이 된다.

export type FocusModule = { module_id: string; order: number; status: string };

const ERROR = "error";
const ANOMALY = "anomaly";
const CURRENT = new Set(["running", "waiting_input"]);

function firstBy(modules: FocusModule[], match: (status: string) => boolean): string | null {
  const hit = [...modules]
    .sort((left, right) => left.order - right.order)
    .find((module) => match(String(module.status).toLowerCase()));
  return hit ? hit.module_id : null;
}

export function computeFocusModuleId(modules: FocusModule[]): string | null {
  if (!modules.length) return null;
  return (
    firstBy(modules, (s) => s === ERROR) ??
    firstBy(modules, (s) => s === ANOMALY) ??
    firstBy(modules, (s) => CURRENT.has(s))
  );
}

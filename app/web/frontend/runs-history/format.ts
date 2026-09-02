/** 드릴다운 행의 시각 표기.
 *
 *  app.js 의 formatRunTimestamp 를 복제했다 — 예약 코드가 원본을 계속 쓰므로
 *  옮길 수 없다(설계 §3.4). 목록이 이미 하루 안이라 날짜 분기는 뺐다.
 *  중복 1건은 Cycle 6 에서 원본과 함께 사라진다. */
export function formatRunTime(isoString: string | null | undefined): string {
  if (!isoString) {
    return "";
  }
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toLocaleTimeString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

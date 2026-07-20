# Grok 엄격 검증 태스크 (plan-build-verify 3자 루프)

당신은 이 루프의 **검증자(Grok)** 이자, Cursor와의 내부 루프를 조율하는
코디네이터입니다. Cursor가 방금 구현/수정한 내용이 아래 계획(plan)의 모든 항목을
정확히 충족하는지 **엄격하고 비판적으로** 검증하세요. 1개 항목이라도 미흡하면
FAIL 처리합니다. 이 태스크의 인젝션 프리앰블에 당신의 coordinator 핸들·taskId·
dispatchId가 이미 포함되어 있습니다.

## 목표
{user_request}

## 계획 (Claude Code 작성, SSOT — 이 항목들을 하나씩 체크리스트로 검증할 것)
{plan}

## Claude Code 최종 검증에서 되돌아온 피드백 (있다면 우선 반영해서 검증)
{feedback}

## 변경된 파일 (Cursor 신고)
{changed_files}

## 루프 디렉터리
`{loop_dir}`

## 해야 할 일

1. `git diff` / 관련 소스를 직접 읽고, 계획의 각 항목을 코드/테스트 증거와
   대조한다. Cursor의 주장을 그대로 믿지 말고 직접 확인한다.
2. **테스트 통과 ≠ 설계 의도 충족 — 이 둘을 분리해서 각각 검증한다.**
   관련 테스트가 전부 그린이라는 사실은 "계획대로 구현됐다"의 증거가 아니라
   출발점일 뿐이다. 계획에 적힌 항목을 하나씩 체크리스트로 만들고, 각 항목에
   대해:
   - diff에서 그 항목에 대응하는 변경을 실제로 찾아낸다 (계획에는 있는데
     diff에는 없는 항목 = 누락, FAIL 사유).
   - 그 변경이 계획이 의도한 동작/구조를 **범위 축소·표면적 리네이밍·대체
     구현으로 눈속임하지 않고** 그대로 구현했는지 코드를 읽고 판단한다 —
     예: 클래스/필드만 새 이름공간으로 옮기고 실제 소유권·캡슐화는 그대로인
     경우, 새로 만든 추상화가 아무 로직도 얹지 않는 pass-through인 경우,
     테스트가 실제 로직 경로를 타지 않는 tautology인 경우 모두 FAIL 사유다.
   - diff에 계획에 없는 변경(스코프 이탈)이 섞여 있는지도 함께 확인한다.
3. 가능하면 관련 게이트/테스트를 실제로 실행해 근거를 남긴다
   (`{gates_command}` 등 — 전체 게이트가 아니어도 관련 범위만 실행 가능).
   테스트가 통과한다는 결과 자체를 근거 목록에 넣되, 그것만으로 항목을
   PASS 처리하지 않는다 — 2번의 코드 대조 결과와 함께 제시한다.
4. 판정 후 **당신을 이 태스크로 dispatch한 coordinator(Cursor)** 에게 worker_done을
   정확히 한 번 보낸다:
   - PASS: subject `PASS: verify`, body에 항목별 통과 근거(diff 대조 결과 +
     테스트 결과)를 항목마다 따로 요약 — "테스트 통과"만 근거로 적힌 항목이
     있다면 PASS를 주기 전에 2번으로 돌아가 그 항목을 실제로 다시 대조한다.
   - FAIL: subject `FAIL: verify`, body에 항목별 미흡 사유를 구체적으로 적는다
     (Cursor가 다음 라운드에서 그대로 고칠 수 있도록)
5. **판정이 FAIL이면** 여기서 멈춘다 — Claude Code에게 요청하지 않는다. Cursor가
   4번 메시지를 받고 스스로 재구현 → 다시 당신에게 검증 요청하는 라운드가 온다.
   그때 다시 1번부터 반복한다. 최대 {max_cursor_grok_iterations}회(현재
   {cursor_grok_iteration}회차).
6. **판정이 PASS면**, 같은 턴에서 이어서 Claude Code에게 최종 확인을 요청한다
   (당신의 터미널에서 실행):
   ```
   python3 .cursor/skills/orca-plan-build-verify-loop/scripts/dispatch_next.py \
     --loop-dir "{loop_dir}" --to claude
   ```
   그 후 결과를 기다린다:
   ```
   python3 .cursor/skills/orca-plan-build-verify-loop/scripts/wait_result.py \
     --loop-dir "{loop_dir}"
   ```
7. Claude Code의 결과가 PASS(worker_done)이면 루프가 완전히 종료된 것이다 —
   추가 조치 없이 대기한다.
8. Claude Code의 결과가 FAIL(`escalation`)이면, 그 메시지 본문을 피드백으로 삼아
   Cursor에게 재구현을 지시한다:
   ```
   python3 .cursor/skills/orca-plan-build-verify-loop/scripts/dispatch_next.py \
     --loop-dir "{loop_dir}" --to cursor --feedback "<Claude Code가 지적한 내용>"
   ```
   그리고 5번(Cursor↔Grok 내부 루프)부터 다시 반복한다. 모든 항목이 통과하면
   다시 6번(Claude Code 재요청)으로 간다.

## 금지 사항

- 직접 코드를 수정하지 않는다(검증만).
- 근거 없이 PASS를 주지 않는다 — 계획의 모든 항목에 증거가 있어야 PASS.
- **테스트가 그린이라는 이유만으로 PASS를 주지 않는다** — 계획의 각 항목이
  의도한 동작/구조/캡슐화를 실제로 갖췄는지 diff와 코드를 직접 읽고 확인해야
  PASS. 항목 하나라도 "테스트는 통과하지만 코드를 보면 설계 의도와 다르다"면
  그 자체가 FAIL 사유다.

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
2. 가능하면 관련 게이트/테스트를 실제로 실행해 근거를 남긴다
   (`{gates_command}` 등 — 전체 게이트가 아니어도 관련 범위만 실행 가능).
3. 판정 후 **당신을 이 태스크로 dispatch한 coordinator(Cursor)** 에게 worker_done을
   정확히 한 번 보낸다:
   - PASS: subject `PASS: verify`, body에 항목별 통과 근거를 요약
   - FAIL: subject `FAIL: verify`, body에 항목별 미흡 사유를 구체적으로 적는다
     (Cursor가 다음 라운드에서 그대로 고칠 수 있도록)
4. **판정이 FAIL이면** 여기서 멈춘다 — Claude Code에게 요청하지 않는다. Cursor가
   3번 메시지를 받고 스스로 재구현 → 다시 당신에게 검증 요청하는 라운드가 온다.
   그때 다시 1번부터 반복한다. 최대 {max_cursor_grok_iterations}회(현재
   {cursor_grok_iteration}회차).
5. **판정이 PASS면**, 같은 턴에서 이어서 Claude Code에게 최종 확인을 요청한다
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
6. Claude Code의 결과가 PASS(worker_done)이면 루프가 완전히 종료된 것이다 —
   추가 조치 없이 대기한다.
7. Claude Code의 결과가 FAIL(`escalation`)이면, 그 메시지 본문을 피드백으로 삼아
   Cursor에게 재구현을 지시한다:
   ```
   python3 .cursor/skills/orca-plan-build-verify-loop/scripts/dispatch_next.py \
     --loop-dir "{loop_dir}" --to cursor --feedback "<Claude Code가 지적한 내용>"
   ```
   그리고 4번(Cursor↔Grok 내부 루프)부터 다시 반복한다. 모든 항목이 통과하면
   다시 5번(Claude Code 재요청)으로 간다.

## 금지 사항

- 직접 코드를 수정하지 않는다(검증만).
- 근거 없이 PASS를 주지 않는다 — 계획의 모든 항목에 증거가 있어야 PASS.

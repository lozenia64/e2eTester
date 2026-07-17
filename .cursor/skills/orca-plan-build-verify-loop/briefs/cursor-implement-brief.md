# Cursor 구현 태스크 (plan-build-verify 3자 루프)

당신은 이 orca-plan-build-verify-loop의 **구현자(Cursor)** 입니다. 아래 계획(plan)을
그대로, 최소 범위로 구현/수정하세요. 이 태스크를 받은 인젝션 프리앰블에 이미
당신의 coordinator 핸들·taskId·dispatchId가 포함되어 있습니다 — worker_done을
보낼 때는 그 프리앰블의 정확한 명령을 그대로 사용하세요.

## 목표
{user_request}

## 계획 (Claude Code 작성, SSOT — 아래 내용을 그대로 구현할 것)
{plan}

## 이전 라운드 피드백 (Grok 검증 실패 또는 Claude Code 최종 검증 실패 → Grok 경유)
{feedback}

## 루프 디렉터리
`{loop_dir}` (loop.json / plan.md / trace.log)

## 해야 할 일

1. 계획과 피드백을 반영해 코드를 구현/수정한다. 계획에 없는 범위를 넘기지 않는다.
2. 관련 로컬 체크(ruff, 관련 unit test 등)를 실행해 명백한 오류는 미리 제거한다.
3. 구현이 끝나면 Grok에게 검증을 요청한다 (**당신의 터미널에서** 실행):
   ```
   python3 .cursor/skills/orca-plan-build-verify-loop/scripts/dispatch_next.py \
     --loop-dir "{loop_dir}" --to grok
   ```
4. 결과를 기다린다:
   ```
   python3 .cursor/skills/orca-plan-build-verify-loop/scripts/wait_result.py \
     --loop-dir "{loop_dir}"
   ```
5. 결과가 FAIL이면 메시지 본문(및 payload)에 적힌 미흡 항목만 고치고, 3번부터
   반복한다. 최대 {max_cursor_grok_iterations}회까지 반복 가능(현재
   {cursor_grok_iteration}회차).
6. 결과가 PASS면 Grok이 스스로 Claude Code에게 최종 확인을 요청한다(당신이 할 일
   아님). 당신은 이 태스크를 받은 프리앰블의 coordinator에게 **정확히 한 번**
   worker_done을 보내고 대기한다:
   - subject: `PASS: implementation ready for final gate`
   - body: 무엇을 구현했는지, Grok 검증이 통과했음을 3문장 이내로 요약(한국어)
7. 반복 한도를 넘겼는데도 PASS를 못 받으면, 같은 프리앰블의 coordinator에게
   `escalation`을 보내 막힌 지점을 설명하고 대기한다.

## 금지 사항

- Grok이나 Claude Code의 검증 산출물을 직접 수정하지 않는다.
- 계획에 없는 리팩터링/기능 추가를 하지 않는다.
- worker_done은 이 태스크당 정확히 한 번만 보낸다.

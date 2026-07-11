## 변경 요약

<!-- 무엇을, 왜 바꿨는지 -->

## 문서 정합성 체크리스트 (Definition of Done)

> 규칙: [docs/DOCS_GOVERNANCE.md](../docs/DOCS_GOVERNANCE.md). 코드를 바꿨다면 짝이 되는 문서를 같은 PR에서 갱신하세요.

- [ ] `python3 scripts/ci/run_all_gates.py --profile full` 가 통과한다(로컬/CI). 규칙: [docs/CI.md](../docs/CI.md).
- [ ] `python3 scripts/check_docs_consistency.py` 가 통과한다(로컬/CI).
- [ ] `python3 scripts/check_architecture_gates.py` 가 통과한다(AG-001~003).
- [ ] `manifest.yaml` 추가·변경 시 짝이 되는 `docs/scenarios/{code}.md` 갱신(모듈/순서/의존성/`workflow_step`/타임아웃).
- [ ] 사이트 흐름·selector 변경 시 해당 시나리오 문서 단계 설명 갱신.
- [ ] API 라우트 추가·변경·삭제 시 `E2E_ARCHITECTURE.md` §5.2 갱신.
- [ ] 환경변수 추가·변경 시 `README.md` + `.env.example` 갱신.
- [ ] 런타임 기본값(모델 체인 등) 변경 시 관련 문서/예시 갱신.
- [ ] SSOT 매트릭스를 위반하는 중복 서술을 새로 추가하지 않음(필요 시 링크 참조).

## 변경 요약

<!-- 무엇을, 왜 바꿨는지 -->

## 문서 정합성 (DoD)

> [docs/DOCS_GOVERNANCE.md](../docs/DOCS_GOVERNANCE.md)

- [ ] `python3 scripts/ci/run_all_gates.py --profile full` 통과
- [ ] 커버리지 하락 없음 (`python3 scripts/ci/run_all_gates.py --gate coverage`)
- [ ] `python3 scripts/check_docs_consistency.py` 통과
- [ ] manifest 변경 → `docs/scenarios/{code}.md` 갱신
- [ ] API 변경 → `docs/E2E_ARCHITECTURE.md` §5.2 갱신
- [ ] env 변경 → `docs/INSTALL.md` + `.env.example`
- [ ] SSOT 중복 서술 없음

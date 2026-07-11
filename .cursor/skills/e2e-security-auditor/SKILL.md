---
name: e2e-security-auditor
description: >-
  Security review for e2eTester orchestration changes (PII, auth, API).
  Used by e2e-orchestrator Quality Council when conditional.
disable-model-invocation: true
---

# e2e Security Auditor (QC-S)

Readonly security review.

## Inputs

- `<run_dir>/intake.json` → risk_flags, touch_surfaces
- `<run_dir>/implementation-notes.md`
- Git diff of changed files

## Focus areas

1. PII not on Run/Suite blobs or WebSocket payloads (RunInputStore only)
2. Auth/JWT cookie handling if `app/auth/` touched
3. New API routes: authz, scoping by `allowed_system_codes`
4. OTP relay / trigger token handling
5. No secrets in logs or artifacts

## Output

Write `<run_dir>/security-report.json`:

```json
{
  "passed": true,
  "issues": []
}
```

Set `passed: false` for high-severity findings.

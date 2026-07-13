# Subagent Map

e2e skill contracts delegate to **Cursor built-in subagent types only**. Never modify subagent definitions.

| e2e Skill | subagent_type | readonly |
|-----------|---------------|----------|
| e2e-intake | generalPurpose | yes |
| e2e-researcher | generalPurpose | yes |
| e2e-domain-scout | explore | yes |
| e2e-scenario-analyst | explore | yes |
| e2e-manifest-planner | planner | yes |
| e2e-platform-architect | planner | yes |
| e2e-selector-healer | generalPurpose | yes |
| e2e-docs-guardian | generalPurpose | yes |
| e2e-implementer | implementer | no |
| e2e-docs-writer | docs-writer | no |
| e2e-test-runner | test-runner | no |
| e2e-code-reviewer | bugbot | yes |
| e2e-security-auditor | security-review | yes |
| e2e-release-judge | verifier | yes |

## Task prompt injection

Each Task must include:

1. The target e2e skill name and path to its `SKILL.md` under `.cursor/skills/`
2. `run_dir` and `workspace` absolute paths
3. `context_variables` from `run.json`
4. Explicit read/write artifact paths from [artifacts-contract.md](artifacts-contract.md)
5. Relevant excerpts from [domain-context.md](domain-context.md)

The subagent executes the e2e skill contract; it does not invent a parallel workflow.

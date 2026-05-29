# Issue Tracker Configuration

**Tracker type:** GitHub Issues

**Repository:** https://github.com/setikites/anaplan-openapi

**How skills use this:**
- `to-issues` creates new GitHub issues via `gh issue create`
- `triage` reads/applies labels and comments via `gh` CLI
- `to-prd` creates issues for PRD-like work

**Where issues live:** https://github.com/setikites/anaplan-openapi/issues

## Creating an issue

Skills will use:
```bash
gh issue create --title "..." --body "..." --label "needs-triage"
```

## Labeling and state transitions

See `docs/agents/triage-labels.md` for label meanings and the triage workflow.

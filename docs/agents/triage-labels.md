# Triage Labels

This project uses five standard triage labels to move issues through their lifecycle.

| Label | Meaning | Action |
|-------|---------|--------|
| `needs-triage` | Issue received; maintainer must evaluate | Maintainer reads and assesses |
| `needs-info` | Needs clarification or more details from reporter | Waiting on reporter response |
| `ready-for-agent` | Fully specified, no human input needed; AFK agent can pick up | Assign to agent or add to agent queue |
| `ready-for-human` | Needs human implementation or decision | Assign to human or schedule for review |
| `wontfix` | Will not be addressed | Close issue |

## Workflow

1. Issue created → labeled `needs-triage`
2. Maintainer evaluates:
   - If unclear → `needs-info` (wait for reporter)
   - If clear and agent-ready → `ready-for-agent`
   - If needs human → `ready-for-human`
   - If out of scope → `wontfix` (close)
3. When work completes → remove label and close issue

## Using these labels with skills

The `triage` skill reads these labels to understand issue state. The `to-issues` skill applies them when creating new issues.

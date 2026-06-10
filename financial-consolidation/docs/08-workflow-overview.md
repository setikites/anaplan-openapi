# Workflow Endpoints — Overview

Source: https://help.anaplan.com/workflow-endpoints-6f8a2bda-bb83-4983-9edc-d0ec17d15167

Last Modified: June 13, 2025

## Overview

"Control workflow processes with the Anaplan Financial Consolidation API."

## Key Capabilities

1. **Start workflow processes** — Trigger workflows, such as those containing data exports to external systems
2. **Stop workflow processes** — Halt running workflows
3. **Query workflow status** — Check the state of initiated workflows, including long-running processes

## Available Endpoints

- `POST /process/start/{path}/{workflow_name}` — Start workflow process
- `POST /process/stop/{path}/{workflow_name}` — Stop a workflow process
- `GET /process/state/{path}/{workflow_name}` — Get the state of a workflow process

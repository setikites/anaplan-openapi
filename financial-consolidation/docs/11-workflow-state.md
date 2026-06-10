# Get the State of a Workflow Process

Source: https://help.anaplan.com/get-the-state-of-a-workflow-process-ac96cbd6-98c1-45d2-8fbf-eb3a5a4c2b56

Last Modified: June 17, 2025

## Method and Endpoint

**GET** `/process/state/{path}/{name_of_workflow}`

## Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `path` | string | Folder location in Explorer | `Workflows/Other` |
| `name_of_workflow` | string | Workflow file name | `Compliance` |

## Request Example

```bash
curl --location GET 'https://fluenceapi-prod.fluence.app/api/v2305.1/process/state/Workflows/Other/Compliance' \
--header 'Tenant: CustomerTenant' \
--header 'Content-Type: application/json' \
--header 'X-API-TOKEN: 73ca5973-ce3e-4cc6-b2d4-b09a99770ccf'
```

## Response

The endpoint "always returns a `200 OK` success message and a run ID."

An invalid path or workflow name returns a null UUID: `00000000-0000-0000-0000-00000000000`

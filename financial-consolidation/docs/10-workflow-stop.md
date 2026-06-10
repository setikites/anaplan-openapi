# Stop a Workflow Process

Source: https://help.anaplan.com/stop-a-workflow-process-61a4045f-4ed3-406b-86d9-a96e6ecb4597

Last Modified: June 13, 2025

## Overview

This endpoint terminates a running Workflow process within the Explorer module.

## Method and Endpoint

**POST** `/process/stop/{path}/{name_of_workflow}`

## Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `path` | string | The path to the workflow file in Explorer | `ImportsandExports` |
| `name_of_workflow` | string | The name of the workflow file in Explorer | `ModelExport` |

## cURL Example

```bash
curl --location POST 'https://fluenceapi-prod.fluence.app/api/v2305.1/process/stop/ImportsandExports/ModelExport' \
--header 'TENANT: CustomerTenant' \
--header 'X-API-TOKEN: 73ca5973-ce3e-4cc6-b2d4-b09a99770ccf'
```

## Response

A successful request returns a `200 OK` response.

## Notes

The published cURL example in the docs incorrectly uses `/start` instead of `/stop` — the correct endpoint based on the description and the endpoint overview is `/process/stop/...`.

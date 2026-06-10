# Start Workflow Process

Source: https://help.anaplan.com/start-workflow-process-0e412efb-e168-4c94-818f-bb6bc550f493

Last Modified: June 13, 2025

## Overview

This endpoint allows you to "command the Anaplan Financial Consolidation server to start a workflow process within the specified folder(s) in the Explorer module."

## Method and Endpoint

**POST** `/process/start/{path}/{name_of_workflow}`

## Content Type

JSON

## Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `path` | string | The path to the workflow file in Explorer | `ImportsandExports` |
| `name_of_workflow` | string | The name of the workflow file in Explorer | `ModelExport` |

## Request Body

Include the parameters for the start task within the workflow process, or use `[]` if no parameters are needed.

## cURL Example

```bash
curl --location POST 'https://fluenceapi-prod.fluence.app/api/v2305.1/process/start/ImportsandExports/ModelExport' \
--header 'TENANT: CustomerTenant' \
--header 'X-API-TOKEN: 73ca5973-ce3e-4cc6-b2d4-b09a99770ccf'
```

## Response

A successful request generates a `200 OK` response.

## Notes

"Special characters that are used in the request, such as '?', '&', and '/', aren't recommended to be used in the name of the Explorer module folders or Workflow processes."

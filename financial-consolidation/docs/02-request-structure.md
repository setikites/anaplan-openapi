# Structure of an API Request

Source: https://help.anaplan.com/structure-of-an-api-request-bcddc03e-9c46-4174-9bae-347cf77a45d4

## Overview

The Financial Consolidation API requires requests formatted to exact specifications, incorporating an HTTP verb, root URL, API version, endpoint, query parameters, headers, and request body.

**Example structure:** `GET https://fluenceapi-prod.fluence.app/api/v2305.1/odata/ClientSchemaTable`

## Core Components

### HTTP Verb/Method

Supported: GET, POST, PUT, DELETE

### Root URL

`https://fluenceapi-prod.fluence.app` — the unique hostname.

### API Version

`/api/v2305.1` — current version, included after the root URL and before endpoints.

### Endpoint/Resource Path

Identifies specific resources using hierarchical path segments separated by forward slashes.

| Endpoint prefix | Purpose | Example |
|-----------------|---------|---------|
| `/odata` | Retrieve, update, delete, add data records | `GET /api/v2305.1/odata/ClientPathParam` |
| `/process` | Manage workflow tasks | `GET /api/v2305.1/process/start/ImportandExports/Data/ModelExport` |
| `/models` | Retrieve dimension lists | `GET /api/v2305.1/models/Consolidations/Dimensions` |
| `/metadata` | Retrieve dimension properties | `GET /api/v2305.1/metadata/Dimensions` |
| `/users` | Manage user roles and permissions | `GET /api/v2305.1/users` |

### Query Parameters

Optional key-value pairs after `?` that filter, sort, and specify data retrieval criteria. Multiple parameters separated with `&`.

**Example:** `?Page=1&PageSize=100`

### Headers

| Header | Description |
|--------|-------------|
| `TENANT` | The tenant where data resides |
| `Content-Type` | Data format (e.g., `application/json`) |
| `X_API_TOKEN` | Valid API token created by an administrator |

### Request Body

Data payload (JSON, CSV) sent with POST and PUT methods. GET requests typically omit bodies.

## Response Codes

| Code | Meaning |
|------|---------|
| `200 OK` | Successful request |
| `204 No Content` | Successful with no response body |
| `400 Bad Request` | Incorrect or missing parameters |
| `401 Unauthorized` | Invalid or malformed authentication token |
| `403 Forbidden` | Insufficient permissions |
| `404 Not Found` | Resource unavailable |
| `405 Method Not Allowed` | Incorrect HTTP verb |
| `406 Not Acceptable` | Unsupported response format |
| `409 Conflict` | Resource conflict |
| `410 Gone` | Resource moved or tenant changed |
| `415 Unsupported Media Type` | Unsupported request body format |
| `429 Too Many Requests` | Excessive request rate |
| `500 Internal Server Error` | Request processing failure |
| `502 Bad Gateway` | Network/DNS issues |
| `503 Service Unavailable` | Service unable to process |
| `504 Gateway Timeout` | Network gateway issues |

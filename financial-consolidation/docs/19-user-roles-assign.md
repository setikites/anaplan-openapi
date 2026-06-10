# Assign User Roles

Source: https://help.anaplan.com/assign-user-roles-c0dabed5-b2c3-448f-813d-36e724bd5775

Last Modified: June 17, 2025

## Overview

Assigns new roles to users within the Anaplan Financial Consolidation API.

## Method and Endpoint

**PUT** `/user/{username}/roles`

Note: singular `/user` (not `/users`) — confirmed by the docs.

## Parameters

| Parameter | Description |
|-----------|-------------|
| `username` | The Financial Consolidation app username (not the user's email address) |

## Request Example

```bash
curl --location 'https://fluenceapi-prod.fluence.app/api/v2305.1/user/john.doe@fluence.app/roles' \
--header 'TENANT: CustomerTenant' \
--header 'X-API-TOKEN: 73ca5973-ce3e-4cc6-b2d4-b09a99770ccf' \
--data-raw '[
    "Controller",
    "Reviewer"
]'
```

## Response Example

Returns all roles assigned to the user, including both existing and newly assigned roles:

```json
[
    "Admin",
    "Controller",
    "Reviewer"
]
```

## Notes

- Request body is a JSON array of role name strings
- Response is additive — includes pre-existing roles alongside the newly assigned ones

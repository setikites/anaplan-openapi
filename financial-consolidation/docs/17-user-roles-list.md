# List Roles for a User

Source: https://help.anaplan.com/list-roles-for-a-user-582f9dfa-1f2b-4e67-a98b-120e58a9f5a9

Last Modified: June 17, 2025

## Overview

Retrieves the roles assigned to a specific user. Supports automation workflows such as cloning user roles during onboarding.

## Method and Endpoint

**GET** `/user/{username}/roles`

Note: singular `/user` (not `/users`) — confirmed by the docs.

## Parameters

| Parameter | Description |
|-----------|-------------|
| `username` | The Financial Consolidation app username, not the user's email address |

## Request Example

```bash
curl --location 'https://fluenceapi-prod.fluence.app/api/v2305.1/user/john.doe@fluence.app/roles' \
--header 'TENANT: CustomerTenant' \
--header 'X-API-TOKEN: 73ca5973-ce3e-4cc6-b2d4-b09a99770ccf'
```

## Response Example

```json
[
    "Admin",
    "Controller",
    "Preparer",
    "Reviewer"
]
```

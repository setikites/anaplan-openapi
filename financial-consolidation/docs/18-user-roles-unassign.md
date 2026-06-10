# Unassign User Roles

Source: https://help.anaplan.com/unassign-user-roles-cf53e027-f854-4195-a445-0ee8347cf010

## Overview

Unassign roles from existing users to adjust user permissions as responsibilities change.

## Method and Endpoint

**DELETE** `/user/{username}/roles`

Note: singular `/user` (not `/users`) — confirmed by the docs.

## Parameters

| Parameter | Description |
|-----------|-------------|
| `username` | "The Financial Consolidation app username, not the user's email address." |

## Example Request

```bash
curl --location --request DELETE 'https://fluenceapi-prod.fluence.app/api/v2305.1/user/john.doe@fluence.app/roles' \
--header 'TENANT: CustomerTenant' \
--header 'Content-Type: application/json' \
--header 'X-API-TOKEN: ••••••' \
--data '"Controller"'
```

This example removes the Controller role from user john.doe@fluence.app.

## Response

Successful `200 OK` returns the remaining user roles:

```json
[
    "Admin"
]
```

## Notes

- Request body is a single role name as a JSON string (not an array) — e.g., `"Controller"`

# Update User Profile

Source: https://help.anaplan.com/update-user-profile-dbaa6715-638c-4720-b4f4-f6788ecc1873

Last Modified: June 17, 2025

## Overview

Modify user data within a tenant. Can update email addresses, enable/disable accounts, and manage role assignments.

## Method and Endpoint

**PUT** `/users`

## Request Example

```bash
curl --location --request PUT 'https://fluenceapi-prod.fluence.app/api/v2305.1/users' \
--header 'TENANT: CustomerTenant' \
--header 'Content-Type: application/json' \
--header 'X-API-TOKEN: 73ca5973-ce3e-4cc6-b2d4-b09a99770ccf' \
--data-raw '{
    "userName": "asmythe@fluence.app",
    "fullName": "Adam Smythe",
    "isDisabled": false,
    "email": "asmythe@acme.com",
    "roles": [
        "Admin",
        "Preparer"
    ]
}'
```

## Request Body Fields

- `userName`: User's login identifier
- `fullName`: User's display name
- `isDisabled`: Boolean flag to enable/disable account access
- `email`: User's email address
- `roles`: Array of assigned role names

## Response

Successful `200 OK` with updated user information:

```json
{
    "userId": 4413,
    "userName": "asmythe@fluence.app",
    "fullName": "Adam Smythe",
    "isDisabled": false,
    "email": "asmythe@acme.com",
    "roles": [
        "Admin",
        "Preparer"
    ]
}
```

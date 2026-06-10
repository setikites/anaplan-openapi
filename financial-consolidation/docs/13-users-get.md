# Get User Information

Source: https://help.anaplan.com/get-user-information-d7b672ee-2777-4adb-a933-3418a9929323

Last Modified: June 17, 2025

## Overview

Retrieves a roster of users within a tenant. No additional parameters or request body required.

## Method and Endpoint

**GET** `/users`

## cURL Example

```bash
curl --location 'https://fluenceapi-prod.fluence.app/api/v2305.1/users' \
--header 'TENANT: CustomerTenant' \
--header 'X-API-TOKEN: 73ca5973-ce3e-4cc6-b2d4-b09a99770ccf'
```

## Response Example

```json
[
  {
    "userId": 3,
    "userName": "jdoe@fluence.app",
    "fullName": "Jane Doe",
    "isDisabled": false,
    "email": "jdoe@acme.com",
    "roles": ["Admin", "Controller", "Preparer"]
  },
  {
    "userId": 164,
    "userName": "jbay@fluence.app",
    "fullName": "James Bay",
    "isDisabled": false,
    "email": "jbay@acme.com",
    "roles": ["Admin", "Controller", "Preparer", "Reviewer", "Cash Team", "Reporting Manager", "Accounting Manager", "Consolidation Workflow"]
  }
]
```

## Response Fields

- `userId`: Integer identifier
- `userName`: Financial Consolidation app username (not email)
- `fullName`: Display name
- `isDisabled`: Boolean account status
- `email`: User's email address
- `roles`: Array of assigned role names

# Add Users

Source: https://help.anaplan.com/add-users-84d0d1dc-b1ce-4cc3-ba2c-f7fc004aced7

Last Modified: June 17, 2025

## Method and Endpoint

**POST** `/users`

## Request

- Tenant must be specified in the header
- New user data sent in the request body as a JSON array
- No query parameters required

## cURL Example

```bash
curl --location 'https://fluenceapi-prod.fluence.app/api/v2305.1/users' \
--header 'TENANT: CustomerTenant' \
--header 'Content-Type: application/json' \
--header 'X-API-TOKEN: 73ca5973-ce3e-4cc6-b2d4-b09a99770ccf' \
--data-raw '[
    {
        "username": "asmith@fluence.app",
        "fullName": "Adam Smith",
        "isdisabled": false,
        "email": "asmith@acme.com",
        "roles": [
            "Admin",
            "Controller",
            "Preparer"
        ]
    }
]'
```

## Response

A successful `200 OK` response echoes the submitted data:

```json
{
    "userName": "asmythe@fluence.app",
    "fullName": "Adam Smythe",
    "isDisabled": false,
    "email": "asmythe@acme.com",
    "roles": [
        "Admin",
        "Controller",
        "Preparer"
    ]
}
```

## Notes

- Request body is a JSON array (can add multiple users at once)
- Field name casing may differ between request (`isdisabled`) and response (`isDisabled`) — needs verification

# Delete User Account from a Tenant

Source: https://help.anaplan.com/delete-user-account-from-a-tenant-89c49325-8ed4-4cbd-aa56-fe2b5645d4b1

## Method and Endpoint

**DELETE** `/users/{username}`

## Parameters

| Parameter | Description |
|-----------|-------------|
| `username` | The Financial Consolidation app username (not email address) |

## Example Request

```bash
curl --location --request DELETE 'https://fluenceapi-prod.fluence.app/api/v2305.1/users/wile.e.coyote@acme.com' \
--header 'TENANT: CustomerTenant' \
--header 'X-API-TOKEN: 73ca5973-ce3e-4cc6-b2d4-b09a99770ccf'
```

## Response

The API returns `200 OK` regardless of whether the user exists. "Use the Get user information request to validate the deletion."

## Notes

- No 404 on missing user — always 200
- `username` in path is the app username, not the email address

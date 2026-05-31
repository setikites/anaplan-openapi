# Authentication API Specification

## Overview

The Authentication API generates tokens for use with other Anaplan APIs. It supports three authentication methods:
1. **HTTP Basic Auth** - username/password
2. **CA Certificate Auth** - certificate-based authentication
3. **Token Refresh** - refresh existing tokens

## Sources

- **Postman Collection**: `authentication/postman-spec.yaml`
- **OpenAPI Spec**: `authentication/authentication-openapi.json`
- **Apiary Docs**: https://anaplanauthentication.docs.apiary.io/
- **Live Testing**: Tested against live Anaplan instance

## Testing

### Unit/Integration Tests

Run OpenAPI validation:
```bash
uv run validate.py authentication/authentication-openapi.json
```

Run all tests:
```bash
uv run pytest tests/
```

### Live API Tests

Live API tests require credentials and are skipped by default. To run them:

```bash
ANAPLAN_USERNAME=your_user \
ANAPLAN_PASSWORD=your_pass \
uv run pytest tests/test_auth_integration_live.py --live
```

#### With CA Certificate Authentication

```bash
ANAPLAN_USERNAME=your_user \
ANAPLAN_PASSWORD=your_pass \
ANAPLAN_CA_CERT_PATH=/path/to/cert.pem \
ANAPLAN_CA_SIGNATURE="signature_payload" \
uv run pytest tests/test_auth_integration_live.py --live
```

## Endpoints

### POST /token/authenticate

Generate an authentication token.

**Supports:**
- HTTP Basic Auth (`username:password` base64-encoded in `Authorization: Basic` header)
- CA Certificate Auth (certificate and signature in request body)

**Response:** 200 with tokenInfo containing:
- `tokenValue` - The authentication token
- `tokenId` - Token identifier
- `expiresAt` - Expiration timestamp (milliseconds)
- `refreshTokenId` - ID for token refresh

### POST /token/refresh

Refresh an existing authentication token.

**Headers:**
- `Authorization: AnaplanAuthToken {token}` - Existing token

**Response:** 200 with new tokenInfo

### GET /token/validate

Validate and get details for an authentication token.

**Headers:**
- `Authorization: AnaplanAuthToken {token}` - Token to validate

**Response:** 200 with tokenInfo and userInfo containing:
- `userGuid` - User GUID
- `userId` - User ID (email)
- `customerGuid` - Customer GUID

### POST /token/logout

Invalidate an authentication token.

**Headers:**
- `Authorization: AnaplanAuthToken {token}` - Token to invalidate

**Response:** 204 No Content

## Security Schemes

The spec defines four security schemes:

1. **BasicAuth** - HTTP Basic authentication
2. **BearerAuth** - Bearer token (documented for compatibility)
3. **AnaplanAuth** - Anaplan custom token header
4. **CACertAuth** - CA certificate authentication

Each endpoint specifies which schemes it supports.

## Known Discrepancies

*(This section will be populated as live testing reveals any differences between the spec and actual API behavior)*

### Error Handling

- **Invalid credentials (401)**: Returned when username/password are incorrect
- **Malformed headers (400)**: May be returned for malformed Authorization headers
- **Expired tokens (401)**: Returned when attempting to use an expired token
- **Revoked tokens (401)**: Returned after logout

### Undocumented Behaviors

*(Findings from live testing will be documented here)*

## Test Coverage

- ✅ Happy path: authenticate → validate → refresh → validate → logout
- ✅ Error cases: invalid credentials, expired/revoked tokens
- ✅ CA certificate authentication workflow
- ✅ Invalid Authorization header formats
- ✅ Response schema validation

## Next Steps

1. Run live tests with your credentials
2. Document any discrepancies found in the "Undocumented Behaviors" section above
3. Report findings as GitHub issues if spec updates are needed
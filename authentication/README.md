# Authentication API Specification

## Overview

The Authentication API generates tokens for use with other Anaplan APIs. It supports three authentication methods:
1. **HTTP Basic Auth** - username/password
2. **CA Certificate Auth** - certificate-based authentication
3. **Token Refresh** - refresh existing tokens

## Sources

| Source | Available | Notes |
|--------|-----------|-------|
| Apiary docs | ✓ | https://anaplanauthentication.docs.apiary.io/ |
| Postman collection | ✓ | Official Anaplan Collection — "Authentication" folder (Basic Credentials, Certificate Authority Authentication, OAuth 2.0 token requests, Other Authentication Actions) |
| Postman spec (fork) | ✓ | `sources/postman-spec.yaml` — generated from a fork of the official Anaplan collection |
| OpenAPI spec | ✓ | `authentication/authentication-openapi.json` |
| Live testing | ✓ | Tested against live Anaplan instance |

## Testing

Validate the spec and run the unit/contract suite (no credentials needed):

```sh
uv run python scripts/validate.py authentication/authentication-openapi.json
uv run pytest
```

Live tests (`tests/test_auth_integration_live.py`) exercise the full
authenticate → validate → refresh → logout flow plus CA-certificate
authentication against a live instance. Credential setup, certificate
prerequisites, and invocation are documented in
[docs/TESTING.md](../docs/TESTING.md).

The certificate authentication flow matches the community `anaplan-sdk`
implementation: generate a random byte string, sign it with the private key
using SHA512withRSA, and send `encodedData` + `encodedSignedData` to
`/token/authenticate`. See the endpoint documentation below.

## Endpoints

### POST /token/authenticate

Generate an authentication token.

**HTTP Basic Auth:**
- Header: `Authorization: Basic {base64(username:password)}`

**CA Certificate Auth:**
- Header: `Authorization: CACertificate {base64_encoded_certificate}`
- Body (JSON):
  - `certificateChain` - Base64-encoded certificate in PEM format
  - `encodedData` - Base64-encoded random string (100+ bytes)
  - `encodedSignature` - Base64-encoded signature of the random string, signed with the private key using SHA512withRSA

**Response:** 201 Created with tokenInfo containing:
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

The spec defines three security schemes:

1. **BasicAuth** - HTTP Basic authentication (used only on `POST /token/authenticate`)
2. **AnaplanAuth** - Anaplan custom token header (`Authorization: AnaplanAuthToken {token}`)
3. **CACertAuth** - CA certificate authentication (`Authorization: CACertificate {cert}`)

Live testing confirmed that `Bearer {token}` is **rejected** on `/token/validate`, `/token/refresh`, and `/token/logout`:
- `/token/validate` and `/token/refresh` return **400** for a Bearer header
- `/token/logout` returns **401** for a Bearer header

`BearerAuth` was removed from the spec. Tokens issued by this API (via Basic or CA Certificate auth) must always be sent as `AnaplanAuthToken {token}`, not `Bearer {token}`.

Note: OAuth Bearer tokens (issued by the OAuth 2.0 API) have not been tested against these endpoints. They are expected to be incompatible since these endpoints manage AnaplanAuthTokens specifically.

## Known Discrepancies

The following discrepancies between the OpenAPI specification and actual API behavior were discovered during live testing:

### Status Code Variations

- **POST /token/authenticate**: Returns `201 Created`, not `200 OK` as documented in spec
- **POST /token/refresh**: Returns `200 OK` as documented (no variation)

### Token Refresh Behavior

- **POST /token/refresh**: Returns the same token value instead of a new token. The token's internal expiration is extended, but the `tokenValue` itself does not change.

### UUID/GUID Format

- **tokenId and refreshTokenId**: Correctly formatted as OpenAPI 3.0 UUID format (8-4-4-4-12 hex digits with hyphens)
  - Example: `c2fe098f-5d19-11f1-b2db-efadbac143e7` ✓
  
- **userGuid and customerGuid**: **NOT** standard UUID format despite their names
  - Format: 32-character hexadecimal strings with NO hyphens (validated with regex pattern)
  - Pattern: `^[0-9a-f]{32}$`
  - Example: `8a868cd97b120fc7017b36d7331d74be`
  - These are Anaplan's internal identifiers, not RFC 4122 UUIDs
  - Note: OpenAPI has no built-in format for hex strings, so pattern validation is used

### Client-Level Header Validation

- Some invalid Authorization header formats (e.g., `"Basic "` with trailing space) are rejected by the HTTP client library before reaching the API server, preventing end-to-end validation of API error handling for malformed headers.

### Error Handling

- **Invalid credentials (401)**: Returned when username/password are incorrect
- **Malformed headers (400)**: May be returned for malformed Authorization headers
- **Expired tokens (401)**: Returned when attempting to use an expired token
- **Revoked tokens (401)**: Returned after logout

### Undocumented Behaviors

Based on live testing against the Anaplan Authentication API:

- **Token Expiration**: Tokens expire 35 minutes after issue (the spec description says 30 minutes, but live testing shows the API grants 35). The `/token/validate` endpoint returns the current token's expiration details even after refresh.
- **Refresh Token Persistence**: The `refreshTokenId` remains consistent across refresh operations, allowing continuous token refresh without re-authentication.
- **Logout Behavior**: After logout, subsequent validation attempts return `401 Unauthorized`, confirming token revocation is immediate.

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
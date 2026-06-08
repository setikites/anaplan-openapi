# Anaplan SCIM API

## Sources

| Source | Available | Notes |
|--------|-----------|-------|
| Apiary docs | ✓ | https://scimapi.docs.apiary.io/ — primary source |
| Postman collection | ✗ | Not included in official Anaplan Postman collection |
| Live testing | Partial | ResourceTypes and Schemas responses extracted; User CRUD not yet tested |

## Servers

The SCIM API is served from `{region}.api.anaplan.com`. Source: [URL, IP, and allowlist requirements](https://support.anaplan.com/url-ip-and-allowlist-requirements-c8235c7d-8af2-413b-a9ff-d465978806b9).

| Region code | Description | SCIM API base URL |
|-------------|-------------|-------------------|
| us1 | Data Center - US East | `https://api.anaplan.com` |
| us2 | Data Center - US West | `https://api.anaplan.com` |
| us5 | Cloud - US East | `https://api.anaplan.com` |
| us7 | Cloud - US | `https://api.anaplan.com` |
| us9 | Cloud - US | `https://us9.api.anaplan.com` |
| eu1 | Data Center - Netherlands | `https://api.anaplan.com` |
| eu2 | Data Center - Germany | `https://api.anaplan.com` |
| eu3 | Cloud - Europe | `https://eu3.api.anaplan.com` |
| eu4 | Cloud - Europe | `https://api.anaplan.com` |
| eu5 | Cloud - Europe | `https://eu5.api.anaplan.com` |
| gb1 | Cloud - UK | `https://gb1.api.anaplan.com` |
| ap1 | Cloud - Japan | `https://api.anaplan.com` |
| au1 | Cloud - Australia | `https://au1a.api2.anaplan.com` |
| ca1 | Cloud - Canada | `https://ca1a.api.anaplan.com` |
| sg1 | Cloud - Singapore | `https://sg1.api.anaplan.com` |
| ae1 | Cloud - UAE | `https://ae1.api.anaplan.com` |
| in1 | Cloud - India | `https://in1.api.anaplan.com` |
| id1 | Cloud - Indonesia | `https://id1.api.anaplan.com` |
| me1 | Cloud - Saudi Arabia | `https://me1.api.anaplan.com` |

## Base Path

All SCIM endpoints are prefixed with `/scim/1/0/v2`. Example:

```
GET https://api.anaplan.com/scim/1/0/v2/Users
```

## API Scope

Anaplan implements a **subset** of SCIM 2.0 (RFC 7644): **Users and their workspace entitlements only**. Groups and other SCIM resource types are not supported.

## Authentication

All three schemes below were confirmed accepted via live testing against `GET /Users` (issue #44). Each returned 403 (not 401) when authenticated without the `USER_ADMIN` role, proving the auth layer recognizes all three.

| Scheme | Format | Notes |
|--------|--------|-------|
| Anaplan Auth Token | `Authorization: AnaplanAuthToken <token>` | Token from the Authentication API |
| Bearer | `Authorization: Bearer <token>` | Accepts the same AnaplanAuthToken value — not a distinct OAuth 2.0 flow |
| HTTP Basic | `Authorization: Basic <base64(user:pass)>` | Standard HTTP Basic Auth |

The `ServiceProviderConfig` endpoint documents only Basic and AnaplanAuthToken. The Apiary docs also list Bearer. Live testing confirms all three work.

Calls require an active, non-SSO Anaplan user with the `USER_ADMIN` role.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/Users` | List users; supports filtering and pagination |
| POST | `/Users` | Create a user with workspace entitlements |
| GET | `/Users/{id}` | Retrieve a single user |
| PUT | `/Users/{id}` | Full replace of user attributes and entitlements |
| PATCH | `/Users/{id}` | Partial update via SCIM PatchOp |
| GET | `/ServiceProviderConfig` | Retrieve supported SCIM capabilities |
| GET | `/ResourceTypes` | Retrieve supported resource types |
| GET | `/Schemas` | Retrieve attribute metadata for supported schemas |

`DELETE /Users/{id}` is **not documented** in the Apiary docs.

## Filtering and Pagination (`GET /Users`)

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `filter` | string | — | Filter expression: `<field> <op> <value>` |
| `startIndex` | integer | 1 | 1-based start index for pagination |
| `count` | integer | 50 | Results per page; max 100 |

**Filterable fields:** `id`, `externalId`, `userName`, `name.familyName`, `name.givenName`, `active`

**Supported filter operators:** `Eq`, `Ne`, `Pr`, `Gt`, `Ge`, `Lt`, `Le`

## Entitlements

`entitlements` is an Anaplan extension to the SCIM User schema — not part of core SCIM 2.0. It represents a user's workspace access.

| `type` value | Meaning |
|--------------|---------|
| `WORKSPACE` | Array of individual workspace objects (`value` = workspace ID, `display` = workspace name) |
| `WORKSPACE_IDS` | Single object; `value` is a comma-delimited list of workspace GUIDs |
| `WORKSPACE_NAMES` | Single object; `value` is a comma-delimited list of workspace names (escaped quotes) |

Responses typically include all three `type` variants for the same workspace set. On create/update requests, send `WORKSPACE` objects. Limit: 50 workspaces per create call.

## Key Constraints

- Visiting users are not supported
- Max 100 users per `GET /Users` call
- Max 50 workspaces per `POST /Users` call
- Entitlement updates may be partially successful (watch for 207 responses)
- Requires active, non-SSO user with `USER_ADMIN` role

## Live API Responses

### GET /ResourceTypes

```
GET /scim/1/0/v2/ResourceTypes
Host: https://api.anaplan.com
Accept: application/json
```

```json
{"schemas":["urn:ietf:params:scim:api:messages:2.0:ListResponse"],"totalResults":1,"startIndex":1,"itemsPerPage":10,"Resources":[{"schemas":["urn:ietf:params:scim:schemas:core:2.0:ResourceType"],"meta":{"resourceType":"ResourceType","location":"https://api.anaplan.com/scim/1/0/v2/ResourceTypes/User"},"id":"User","name":"User","endpoint":"/Users","description":"User Account","schema":"urn:ietf:params:scim:schemas:core:2.0:User"}]}
```

### GET /Schemas

```
GET /scim/1/0/v2/Schemas
Host: https://api.anaplan.com
Accept: application/json
```

```json
{"schemas":["urn:ietf:params:scim:api:messages:2.0:ListResponse"],"totalResults":1,"startIndex":1,"itemsPerPage":10,"Resources":[{"meta":{"resourceType":"Schema","location":"https://api.anaplan.com/scim/1/0/v2/Schemas/urn:ietf:params:scim:schemas:core:2.0:User"},"id":"urn:ietf:params:scim:schemas:core:2.0:User","name":"User","description":"User Account","attributes":[{"name":"id","type":"string","multiValued":false,"description":"Unique identifier for a user by Service Provider. Note - CaseExact=false which is not per RFC.","required":true,"caseExact":false,"mutability":"readOnly","returned":"always","uniqueness":"server"},{"name":"externalId","type":"string","multiValued":false,"description":"Unique Identifier for a user as defined by provisioning client. Note - CaseExact=false which is not per RFC.","required":false,"caseExact":false,"mutability":"readWrite","returned":"default","uniqueness":"none"},{"name":"userName","type":"string","multiValued":false,"description":"Username of the User. It is a Required attribute and uniquely identifies a User","required":true,"caseExact":false,"mutability":"readOnly","returned":"default","uniqueness":"server"},{"name":"name","type":"complex","subAttributes":[{"name":"familyName","type":"string","multiValued":false,"description":"Family name of the User","required":true,"caseExact":false,"mutability":"readWrite","returned":"default","uniqueness":"none"},{"name":"givenName","type":"string","multiValued":false,"description":"Given name of the User","required":true,"caseExact":false,"mutability":"readWrite","returned":"default","uniqueness":"none"},{"name":"formatted","type":"string","multiValued":false,"description":"Formatted name of the User","required":false,"caseExact":false,"mutability":"readOnly","returned":"default","uniqueness":"none"}],"multiValued":false,"description":"Components of users real name","required":true,"caseExact":false,"mutability":"readWrite","returned":"default","uniqueness":"none"},{"name":"displayName","type":"string","multiValued":false,"description":"Display Name of the User. It is generated by concatenating givenName and familyName.","required":false,"caseExact":false,"mutability":"readOnly","returned":"default","uniqueness":"none"},{"name":"active","type":"boolean","multiValued":false,"description":"Used to manage whether user can log into Anaplan system or not","required":false,"caseExact":false,"mutability":"readWrite","returned":"default","uniqueness":"none"},{"name":"entitlements","type":"complex","subAttributes":[{"name":"value","type":"string","multiValued":false,"description":"The target resourceId of an entitlement. e.g. a WorkspaceId","required":false,"caseExact":false,"mutability":"readWrite","returned":"default","uniqueness":"none"},{"name":"display","type":"string","multiValued":false,"description":"A human-readable name for the entitlement. e.g. a Workspace 'name'","required":false,"caseExact":false,"mutability":"readWrite","returned":"default","uniqueness":"none"},{"name":"type","type":"string","multiValued":false,"description":"The type of entitlement. e.g. WORKSPACE, or WORKSPACE_IDS for a comma delimited list of workspaces","required":false,"canonicalValues":["WORKSPACE","WORKSPACE_IDS","WORKSPACE_NAMES"],"caseExact":false,"mutability":"readOnly","returned":"default","uniqueness":"none"},{"name":"primary","type":"boolean","multiValued":false,"description":"A Boolean value indicating the 'primary' or preferred attribute value for this attribute. The primary attribute value 'true' MUST appear no more than once.","required":false,"caseExact":false,"mutability":"readOnly","returned":"default","uniqueness":"none"}],"multiValued":true,"description":"A list of entitlements for the User that represents a thing (such as WORKSPACE) the User has.","required":false,"caseExact":false,"mutability":"readWrite","returned":"default","uniqueness":"none"},{"name":"emails","type":"complex","subAttributes":[{"name":"value","type":"string","multiValued":false,"description":"The email address","required":false,"caseExact":false,"mutability":"readWrite","returned":"default","uniqueness":"none"},{"name":"type","type":"string","multiValued":false,"description":"The type of email, current only \"work\" is supported","required":false,"caseExact":false,"mutability":"readOnly","returned":"default","uniqueness":"none"},{"name":"primary","type":"boolean","multiValued":false,"description":"A Boolean value indicating the 'primary' or preferred attribute value for this attribute. The primary attribute value 'true' MUST appear no more than once.","required":false,"caseExact":false,"mutability":"readOnly","returned":"default","uniqueness":"none"}],"multiValued":true,"description":"A list of emails for the User.","required":false,"caseExact":false,"mutability":"readWrite","returned":"default","uniqueness":"none"}]}]}
```

## Testing Coverage

| Endpoint | Happy Path | Error Cases | Notes |
|----------|-----------|-------------|-------|
| `GET /Users` | Partial | — | Auth schemes confirmed (issue #44); full response not yet tested (needs USER_ADMIN role) |
| `POST /Users` | — | — | Not yet tested |
| `GET /Users/{id}` | — | — | Not yet tested |
| `PUT /Users/{id}` | — | — | Not yet tested |
| `PATCH /Users/{id}` | — | — | Not yet tested |
| `GET /ServiceProviderConfig` | — | — | Not yet tested |
| `GET /ResourceTypes` | ✓ | — | Live response captured above |
| `GET /Schemas` | ✓ | — | Live response captured above |

## Discrepancies and Notes

- **`userName` and `displayName` are `readOnly`**: The live `GET /Schemas` response marks both as `mutability: readOnly`. RFC 7644 specifies `userName` as `readWrite`. Anaplan derives `displayName` by concatenating `givenName` and `familyName`, so it cannot be set directly.
- **`id` and `externalId` have `caseExact: false`**: The live schema response flags both as non-RFC — the SCIM standard requires `caseExact: true` for these fields.
- **`active` represented inconsistently in Apiary examples**: The Apiary response examples show `"active": "True"` (string) alongside `"active": true` (boolean) in the same object. The live schema defines it as a boolean; treat the string form as a documentation artifact.
- **`ServiceProviderConfig` claims `patch: false` and `filter: false`**: The Apiary `GET /ServiceProviderConfig` example response shows both as `supported: false`, but the same Apiary docs document a working `PATCH /Users/{id}` endpoint and `filter` query parameter on `GET /Users`. The ServiceProviderConfig example appears outdated.
- **No `DELETE /Users/{id}` in Apiary**: The endpoint is absent from Apiary docs. Do not include it in the spec unless confirmed via live testing.
- **`GET /Users` example uses `localhost:8090`**: The Apiary example response contains `location` URLs pointing to `localhost:8090` — a test artifact, not the production API.
- **Typo in Apiary POST example**: The `Host` header in the `POST /Users` example reads `api.anplan.com` (missing the second `a` in `anaplan`).

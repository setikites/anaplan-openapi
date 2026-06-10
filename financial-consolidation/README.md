# Financial Consolidation API

Anaplan Financial Consolidation API — built on the Fluence platform (Fluence acquired by Anaplan).

## Source documentation

All ~20 documentation pages have been saved under `docs/` for offline reference.

| Doc | URL |
|-----|-----|
| Overview | https://help.anaplan.com/anaplan-financial-consolidation-api-e83345d8-0509-4228-b532-679ee398a9d5 |
| Authentication | https://help.anaplan.com/financial-consolidation-api-authentication-e34c81e9-f00e-46a1-b929-e30468dff320 |
| Request structure | https://help.anaplan.com/structure-of-an-api-request-bcddc03e-9c46-4174-9bae-347cf77a45d4 |
| OData overview | https://help.anaplan.com/odata-endpoint-6460c8af-1559-48dc-9050-a49d3bd1c97d |
| Metadata overview | https://help.anaplan.com/metadata-endpoints-fd30d8b1-4524-4951-97bc-66ac97ca133a |
| Retrieve dimensions in tenant | https://help.anaplan.com/retrieve-dimensions-and-properties-in-a-tenant-74be7205-e781-4d47-940e-de1f2fe7d883 |
| Retrieve dimensions in model | https://help.anaplan.com/retrieve-dimensions-and-properties-in-a-model-fec8a282-eb44-4af4-ae4c-aceb34afa3d0 |
| Retrieve dimension members | https://help.anaplan.com/retrieve-dimension-members-and-their-properties-981b2792-a6e0-48a0-9e05-43e22acf8570 |
| Workflow overview | https://help.anaplan.com/workflow-endpoints-6f8a2bda-bb83-4983-9edc-d0ec17d15167 |
| Start workflow | https://help.anaplan.com/start-workflow-process-0e412efb-e168-4c94-818f-bb6bc550f493 |
| Stop workflow | https://help.anaplan.com/stop-a-workflow-process-61a4045f-4ed3-406b-86d9-a96e6ecb4597 |
| Get workflow state | https://help.anaplan.com/get-the-state-of-a-workflow-process-ac96cbd6-98c1-45d2-8fbf-eb3a5a4c2b56 |
| User management overview | https://help.anaplan.com/user-management-endpoints-1ac319a9-a9cb-4ea9-bb43-a79d64e3231e |
| Get user information | https://help.anaplan.com/get-user-information-d7b672ee-2777-4adb-a933-3418a9929323 |
| Add users | https://help.anaplan.com/add-users-84d0d1dc-b1ce-4cc3-ba2c-f7fc004aced7 |
| Delete user | https://help.anaplan.com/delete-user-account-from-a-tenant-89c49325-8ed4-4cbd-aa56-fe2b5645d4b1 |
| Update user profile | https://help.anaplan.com/update-user-profile-dbaa6715-638c-4720-b4f4-f6788ecc1873 |
| List roles | https://help.anaplan.com/list-roles-for-a-user-582f9dfa-1f2b-4e67-a98b-120e58a9f5a9 |
| Unassign roles | https://help.anaplan.com/unassign-user-roles-cf53e027-f854-4195-a445-0ee8347cf010 |
| Assign roles | https://help.anaplan.com/assign-user-roles-c0dabed5-b2c3-448f-813d-36e724bd5775 |

## Host

`https://fluenceapi-prod.fluence.app` — this is the Fluence platform host, different from all other Anaplan APIs (`api.anaplan.com`, `auth.anaplan.com`, `app.anaplan.com`).

The Fluence platform was acquired by Anaplan. The API is branded as "Anaplan Financial Consolidation" but runs on Fluence infrastructure.

## Authentication

This API uses a custom API key scheme — **not** Bearer or AnaplanAuthToken:

```
X_API_TOKEN: <api-token>
TENANT: <tenant-name>
```

- `X_API_TOKEN`: API token created in the Financial Consolidation Security module by an administrator. Example value: `12345bc3-2929-599c-abc1-23f90aa94x3f`
- `TENANT`: Tenant name as displayed in the Financial Consolidation UI. Must match exactly including spaces/underscores. Required on **every** request.

## API version

Current version: `v2305.1`

Full request URL pattern: `https://fluenceapi-prod.fluence.app/api/v2305.1/{endpoint}`

## Discovered endpoints

From documentation review (all to be added to the spec in a follow-up issue):

### Metadata
- `GET /metadata/Dimensions` — list all dimensions in tenant
- `GET /metadata/models/{modelName}/Dimensions` — list dimensions in a model
- `GET /metadata/Dimensions/{dimensionName}?Page=&PageSize=` — list dimension members (paginated)

### OData (staging tables)
- `GET /odata/{tableName}`
- `POST /odata/{tableName}`
- `PUT /odata/{tableName}`
- `DELETE /odata/{tableName}`

### Workflow
- `POST /process/start/{path}/{workflowName}` — start a workflow
- `POST /process/stop/{path}/{workflowName}` — stop a workflow
- `GET /process/state/{path}/{workflowName}` — get workflow run state

### User management
- `GET /users` — list all users in tenant
- `POST /users` — add user(s)
- `DELETE /users/{username}` — delete a user
- `PUT /users` — update user profile
- `GET /user/{username}/roles` — list roles for a user
- `DELETE /user/{username}/roles` — unassign a role from a user
- `PUT /user/{username}/roles` — assign roles to a user

Note: role endpoints use singular `/user/{username}/roles`, not `/users/{username}/roles` — this appears to be an intentional inconsistency in the API.

## Open questions

1. **Regional deployments**: Only a single production host (`fluenceapi-prod.fluence.app`) is documented. It is unknown whether there are region-specific endpoints for other Anaplan regions (EU, APAC, etc.). The Fluence acquisition may mean this API does not follow Anaplan's usual multi-region deployment model.
2. **Version path in other environments**: `v2305.1` is documented as the current version. It is unknown what the version path looks like in staging/sandbox environments, or whether the version is expected to change over time.
3. **Stop workflow cURL error**: The published cURL example for "Stop a workflow" shows `/process/start/` instead of `/process/stop/` — assumed to be a documentation error. Needs live verification.
4. **User endpoint path inconsistency**: Role management uses `/user/{username}/roles` (singular) while other user endpoints use `/users` (plural). Needs live verification to confirm both forms are correct.
5. **Delete always returns 200**: The docs say DELETE `/users/{username}` returns 200 even for nonexistent users. Needs live verification.
6. **Request body field casing**: The Add Users example shows `isdisabled` in the request body but `isDisabled` in the response. Needs live verification.

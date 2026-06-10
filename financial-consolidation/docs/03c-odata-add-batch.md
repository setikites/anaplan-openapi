# Add Batch Records to a Client Schema Table

Source: https://help.anaplan.com/add-batch-records-to-a-client-schema-table-b38b8ddc-a9b3-40db-84de-fff230e5b997

## Request

**Method:** POST  
**Path:** `/odata/batch/{tableName}`  
**Full URL example:** `https://fluenceapi-prod.fluence.app/api/v2305.1/odata/batch/Consolidation`

Note: path prefix is `/odata/batch/` (not `/odata/{tableName}/batch`).

**Required Headers:**
- `TENANT: CustomerTenant`
- `Content-Type: application/json`

## Request Body

Array of record objects. Each object has the same field structure as the single-record POST.

```json
[
  {
    "Account_Name": "6001",
    "Scenario_Name": "Budget",
    "Date_Name": "2023 Dec",
    "Amount": 25000.00,
    "Text": null,
    "Periodic_Amount": null
  },
  {
    "Account_Name": "6002",
    "Scenario_Name": "Budget",
    "Date_Name": "2023 Dec",
    "Amount": 15000.00,
    "Text": null,
    "Periodic_Amount": null
  }
]
```

## Response

No response body documented.

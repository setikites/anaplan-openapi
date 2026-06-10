# Get Client Schema Table Data

Source: https://help.anaplan.com/get-client-schema-table-data-480986d3-a907-4675-9cdf-1392e95e1a20

## Request

**Method:** GET  
**Path:** `/odata/{tableName}?{filterparameter}`

**Required Headers:**
- `TENANT: CustomerTenant`
- `X_API_TOKEN: <token>`

**Query Parameters:** See `03f-odata-query-params.md`

## Example Request

```
curl -L -X GET 'https://fluenceapi-prod.fluence.app/api/v2305.1/odata/Consolidation?$filter=startswith(Date,'2024')' \
-H 'TENANT: CustomerTenant' \
-H 'X_API_TOKEN: 73ca5973-ce3e-4cc6-b2d4-b09a99770ccf'
```

## Response

Array of row objects. Field names and types vary by table schema.

**Example response:**
```json
[{
  "Account_Name": "1110",
  "Audit_Name": "Source GL",
  "CostCenter_Name": "No CostCenter",
  "Currency_Name": "USD",
  "DataView_Name": "Conversion",
  "Date_Name": "2024 Dec",
  "Entity_Name": "220",
  "Intercompany_Name": "No Entity",
  "Movement_Name": "Closing",
  "Product_Name": "No product",
  "Scenario_Name": "Actual",
  "Amount": 75443.48,
  "Text": "",
  "Periodic_Amount": 0.0
}]
```

When `Page`/`PageSize` are used the response includes pagination fields: `CurrentPage`, `TotalPages`, `TotalRows`.

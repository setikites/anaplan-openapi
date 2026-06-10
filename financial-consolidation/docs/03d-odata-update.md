# Update Client Schema Table Records

Source: https://help.anaplan.com/update-client-schema-table-records-3d280cfb-0bcb-4905-a0e3-11ec9d7bb2ad

## Request

**Method:** PUT  
**Path:** `/odata/{tableName}?{queryparameter}`

**Required Headers:**
- `TENANT: CustomerTenant`
- `Content-Type: application/json`

**Query Parameters:**
- `{queryparameter}`: Column name specifying which rows to update (OData filter expression)

## Request Body

JSON object with field values to write to matched rows.

```json
{
  "Account_Name": "6001",
  "Movement_Name": "Closing",
  "Scenario_Name": "Budget",
  "Date_Name": "2023 Dec",
  "Entity_Name": "120",
  "Amount": 30000.00,
  "Text": null,
  "Periodic_Amount": null
}
```

## Notes

- PUT updates existing rows matching the query parameter; POST inserts new rows.
- Use GET with `$filter` to verify updates.

## Response

No response body documented.

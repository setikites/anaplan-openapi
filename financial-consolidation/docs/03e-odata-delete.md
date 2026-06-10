# Delete Data from Client Schema Table

Source: https://help.anaplan.com/delete-data-from-client-schema-table-e09de78a-f456-441c-9921-8cf833a62279

## Request

**Method:** DELETE  
**Path:** `/odata/{tableName}?{queryparameter}`

**Required Headers:**
- `TENANT: CustomerTenant`
- `Content-Type: application/json`

**Query Parameters:**
- `{queryparameter}` (optional): Column filter to select rows for deletion. Omit to clear all rows while preserving schema.

## Request Body

JSON object with field values identifying rows to delete.

```json
{
  "Account_Name": "6001",
  "Audit_Name": "Reclassification",
  "CostCenter_Name": "000",
  "Currency_Name": "USD",
  "DataView_Name": "Value",
  "Date_Name": "2024 Dec",
  "Entity_Name": "120",
  "Intercompany_Name": "No Intercompany",
  "Movement_Name": "Closing",
  "Product_Name": "No product",
  "Scenario_Name": "Budget",
  "Amount": 25000.00,
  "Text": null,
  "Periodic_Amount": null
}
```

## Response

No response body documented.

# Add a Record to a Client Schema Table

Source: https://help.anaplan.com/add-a-record-to-a-client-schema-table-e1cdae2e-e07a-4e13-819a-6f378d5f7088

## Request

**Method:** POST  
**Path:** `/odata/{tableName}`

**Required Headers:**
- `TENANT: CustomerTenant`
- `Content-Type: application/json`

## Request Body

Single JSON object with dimension and measure fields for the table.

```json
{
  "Account_Name": "6001",
  "Audit_Name": "Reclassification",
  "CostCenter_Name": "000",
  "Currency_Name": "USD",
  "DataView_Name": "Value",
  "Date_Name": "2023 Dec",
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

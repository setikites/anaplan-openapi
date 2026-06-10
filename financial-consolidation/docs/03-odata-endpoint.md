# OData Endpoint

Source: https://help.anaplan.com/odata-endpoint-6460c8af-1559-48dc-9050-a49d3bd1c97d

Last Modified: June 16, 2025

## Overview

OData (Open Data Protocol) is an OASIS standard defining best practices for constructing and utilizing RESTful APIs. The Financial Consolidation OData endpoint exposes client schema staging tables.

## Supported HTTP Methods

| Method | Operation |
|--------|-----------|
| GET | Retrieves information from a single schema table |
| POST | Inserts data into a client schema table |
| PUT | Updates one or more rows in a client schema table |
| DELETE | Removes one or more rows from a table, or clears table contents while preserving schema |

## Endpoint Path

```
/odata/{tableName}
```

(Derived from examples like `GET /api/v2305.1/odata/ClientSchemaTable`)

## Request Requirements

All OData endpoint requests must include:
- `TENANT` header with tenant identifier
- `X_API_TOKEN` header with valid API token
- An intersection of parameters or address the entire table

## Parameter Data Types

| Data Type | Description | Example |
|-----------|-------------|---------|
| string | Alphanumeric sequence of letters and numbers | `{ "Scenario": "Actual" }` |
| integer | Whole number (positive or negative) | `{ "Amount": 519817.0 }` |
| boolean | Represents two options, typically TRUE or FALSE | `1` for true; `0` for false |

## Notes

- The OData endpoint is for staging tables (not directly for model data)
- The full example from request-structure doc: `GET /api/v2305.1/odata/ClientPathParam`

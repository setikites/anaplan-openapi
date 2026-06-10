# Retrieve Dimensions and Properties in a Tenant

Source: https://help.anaplan.com/retrieve-dimensions-and-properties-in-a-tenant-74be7205-e781-4d47-940e-de1f2fe7d883

## Method and Endpoint

**GET** `/metadata/Dimensions`

## Purpose

Retrieve comprehensive dimension and property lists to integrate with external systems. "Reduces manual data entry, and keep data consistent between systems."

## Request Example

```bash
curl --location 'https://fluenceapi-prod.fluence.app/api/v2305.1/metadata/dimensions' \
--header 'TENANT: CustomerTenant' \
--header 'X-API-TOKEN: 73ca5973-ce3e-4cc6-b2d4-b09a99770ccf'
```

## Response Structure

The API returns a JSON array of dimension objects:

- `dimensionName`: Name of the dimension (e.g., "Account")
- `translations`: Available language translations
- `relatedDimension`: Associated dimension reference
- `properties`: Array of property objects
- `processingStatus`: Status indicator

## Property Attributes

Each property object includes:

- `propertyName`: Name identifier
- `propertyType`: Data type (string, Bit, List)
- `standardProperty`: Boolean flag for standard properties
- `reportingProperty`: Boolean flag for reporting use
- `readonlyProperty`: Boolean flag for read-only status
- `processingStatus`: Current processing state
- `typeInfo`: Additional type information

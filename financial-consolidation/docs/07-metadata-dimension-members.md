# Retrieve Dimension Members and Their Properties

Source: https://help.anaplan.com/retrieve-dimension-members-and-their-properties-981b2792-a6e0-48a0-9e05-43e22acf8570

## Method and Endpoint

**GET** `/metadata/Dimensions/{dimensionName}`

## Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `dimensionName` | string | The name of a dimension within a tenant | `Account` |
| `Page` | number | Specifies the desired query page to retrieve | `Page=1` |
| `PageSize` | number | Specifies how many rows to fetch for the page | `PageSize=100` |

## Example Request

```bash
curl --location 'https://fluenceapi-prod.fluence.app/api/v2305.1/metadata/Dimensions/DataView?Page=1&PageSize=100' \
--header 'TENANT: CustomerTenant' \
--header 'X-API-TOKEN: 73ca5973-ce3e-4cc6-b2d4-b09a99770ccf'
```

## Response Structure

- `dimensionMembers`: Array of member objects
- `totalRows`: Total count of dimension members
- `currentPage`: Current page number
- `totalPages`: Total number of pages available

## Member Properties

Each member includes:

- `memberName`: Name of the member
- `memberTag`: Tag identifier (nullable)
- `memberCaption`: Display caption
- `ancestors`: Hierarchy path
- `translations`: Array of translations
- `parentMemberName`: Parent member reference
- `sortOrder`: Sort sequence number
- `isLeaf`: Boolean indicating if member is a leaf node
- `operator`: Operator value (nullable)
- `startDate`/`endDate`: Date range (nullable)
- `memberStorage`: Storage type
- `properties`: Array of property name-value pairs

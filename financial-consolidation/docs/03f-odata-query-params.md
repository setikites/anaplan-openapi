# OData Query Parameters

Source: https://help.anaplan.com/query-parameters-13a7ec52-48cf-45c5-b3f6-d60082b0bb69

All parameters are optional.

## Pagination

| Parameter | Type    | Description                                      | Example        |
|-----------|---------|--------------------------------------------------|----------------|
| `Page`    | integer | Page number to retrieve. Starts at 1.            | `?Page=1`      |
| `PageSize`| integer | Rows per page. Maximum 2500.                     | `?PageSize=500`|

When pagination is used the response includes: `CurrentPage`, `TotalPages`, `TotalRows`.

## Filtering and Querying

| Parameter  | Type    | Description                                                  |
|------------|---------|--------------------------------------------------------------|
| `$filter`  | string  | OData filter expression (see logical operators doc)          |
| `$select`  | string  | Comma-separated column list; `*` for all columns             |
| `$orderby` | string  | Sort expression: `fieldName asc` or `fieldName desc`         |
| `$top`     | integer | Return only the first N records                              |
| `$skip`    | integer | Skip the first N records                                     |
| `$apply`   | string  | Transformations, grouping, aggregation                       |
| `$count`   | boolean | Request a count of matching resources                        |
| `Format`   | string  | Response format: `flat` or `default` (default: `default`)   |

# Retrieve Dimensions and Properties in a Model

Source: https://help.anaplan.com/retrieve-dimensions-and-properties-in-a-model-fec8a282-eb44-4af4-ae4c-aceb34afa3d0

## Method and Endpoint

**GET** `/metadata/models/{modelName}/Dimensions`

## Parameters

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `modelName` | string | The name of the model in your Anaplan Financial Consolidation tenant | Yes |

## Example Request

```bash
curl --location 'https://fluenceapi-prod.fluence.app/api/v2305.1/metadata/models/Consolidation/Dimensions' \
--header 'TENANT: CustomerTenant' \
--header 'X-API-TOKEN: 73ca5973-ce3e-4cc6-b2d4-b09a99770ccf'
```

## Response Structure

```json
[
  {
    "dimensionName": "Account",
    "dimensionType": "Account",
    "translations": "fr",
    "relatedDimension": null,
    "properties": [
      {
        "propertyName": "Classification",
        "propertyType": "list",
        "standardProperty": true,
        "reportingProperty": true,
        "readonlyProperty": false,
        "processingStatus": 0,
        "typeInfo": "Classification"
      }
    ],
    "processingStatus": null
  }
]
```

## Notes

After retrieving dimension and property information, consult the "Dimension properties glossary to identify the purpose and type of each property."

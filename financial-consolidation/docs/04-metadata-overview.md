# Metadata Endpoints — Overview

Source: https://help.anaplan.com/metadata-endpoints-fd30d8b1-4524-4951-97bc-66ac97ca133a

## Overview

The metadata endpoints enable synchronization of dimension information with external applications like planning solutions and reporting tools. These endpoints help organizations "synchronize dimension information with an external application, such as a planning solution."

## Key Benefits

- Eliminates manual upkeep of structural information across systems
- Reduces risks of inconsistencies between platforms
- Enhances operational efficiency through real-time updates
- Improves accuracy of financial information sharing

## Available Queries

1. Dimensions and properties across an entire tenant (`GET /metadata/Dimensions`)
2. Dimensions and properties within a specific model (`GET /metadata/models/{modelName}/Dimensions`)
3. Members and properties within a specific dimension (`GET /metadata/Dimensions/{dimensionName}`)

## Notes

Member keys can be included in queries, though they may have limited relevance outside the Anaplan environment.

# Anaplan Financial Consolidation API — Overview

Source: https://help.anaplan.com/anaplan-financial-consolidation-api-e83345d8-0509-4228-b532-679ee398a9d5

## Overview

The Anaplan Financial Consolidation API enables automation of financial processes through secure, web-based REST services. The API allows users to "control workflows, manage security, retrieve, insert, update, and delete financial data and metadata with external process automations."

## Key Capabilities

- **Data Management**: Upload data to staging tables for validation and transfer into models or fact tables; retrieve financial information such as profit/loss, balance sheet, and cash flow data
- **Metadata Synchronization**: Access dimensions, member relationships, and properties to align with external applications
- **Workflow Automation**: Programmatically start, stop, and monitor workflow processes using Run IDs
- **User Administration**: Bulk user management operations and security configuration

## Technical Characteristics

- Protocol: HTTPS
- Response format: JSON
- Authentication: encrypted API key (X_API_TOKEN header) + TENANT header
- Host: `https://fluenceapi-prod.fluence.app`
- Version path: `/api/v2305.1/`

## Practical Applications

Common use cases include integrating with ERP systems, feeding financial actuals into downstream planning applications, importing budget data from planning platforms, and automating user provisioning and security administration.

## Documentation Structure

- Authentication
- API request structure
- OData endpoints
- Metadata endpoints
- Workflow endpoints
- User management endpoints

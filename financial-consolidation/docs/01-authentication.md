# Financial Consolidation API Authentication

Source: https://help.anaplan.com/financial-consolidation-api-authentication-e34c81e9-f00e-46a1-b929-e30468dff320

## Overview

All requests must include a valid authentication token to "ensure the client and server communication is encrypted and secure, providing an additional layer of protection for your REST API interactions."

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{HOSTNAME}` | REST API URL for your Financial Consolidation environment | `https://fluenceapi-prod.fluence.app` |
| `{TENANT}` | Tenant name as displayed in Financial Consolidation UI (must match exactly, including spaces/underscores) | `CustomerTenant` |
| `{API_TOKEN}` | API token created in Security module; pass as X_API_TOKEN header | `12345bc3-2929-599c-abc1-23f90aa94x3f` |
| `{API_VERSION}` | Current API version included in request URL | `v2305.1` |

## Auth Scheme

- Header: `X_API_TOKEN: <token>` (apiKey type, in header)
- Every request also requires: `TENANT: <tenant-name>` header
- The API token is created in the Financial Consolidation Security module by an administrator

## Notes

The documentation recommends setting up variables in your API development environment to pass parameters through requests, ensuring the correct server, tenant, and API version are targeted alongside the authentication token.

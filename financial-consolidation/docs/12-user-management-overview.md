# User Management Endpoints — Overview

Source: https://help.anaplan.com/user-management-endpoints-1ac319a9-a9cb-4ea9-bb43-a79d64e3231e

## Overview

The API provides security endpoints for automating user management tasks. These capabilities enable administrators to handle bulk operations and adjust security settings efficiently.

## Primary Functions

- **User Discovery**: Retrieve comprehensive user lists including identifiers, names, contact information, enabled/disabled status, and assigned roles
- **User Lifecycle**: Add new users or remove existing accounts from tenants
- **Profile Management**: Modify user details such as email addresses and account activation status
- **Role Administration**: View role assignments, grant roles to users, or revoke role access

## Available Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/users` | Get user information (list all users) |
| POST | `/users` | Add users |
| DELETE | `/users/{username}` | Delete user account from a tenant |
| PUT | `/users` | Update user profile |
| GET | `/user/{username}/roles` | List roles for a user |
| DELETE | `/user/{username}/roles` | Unassign user roles |
| PUT | `/user/{username}/roles` | Assign user roles |

## Notes

- The list/add/delete/update user endpoints use `/users` (plural)
- The role management endpoints use `/user/{username}/roles` (singular `user`) — note the inconsistency

You are an expert at writing OpenAPI 3.0 specifications.

I need you to generate a complete OpenAPI 3.0 JSON spec for a REST API based on the following inputs:

## API Documentation
[https://anaplanauthentication.docs.apiary.io/](https://anaplanauthentication.docs.apiary.io/)

## Sample JSON Responses

### create authentication tokens
REQUEST
curl -X POST --user Username@Company.com:YourPassword https://auth.anaplan.com/token/authenticate

Response 200 (application/json)
{
    "meta": {
        "validationUrl": "https://auth.anaplan.com/token/validate"
    },
    "status": "SUCCESS",
    "statusMessage": "Login successful",
    "tokenInfo": {
        "expiresAt": 1493036651173,
        "tokenId": "9aa99999-1111-11a2-b333-abc11223ab12",
        "tokenValue": "aBCDdefghilMnz30PrD8Iw==.twOZw6fT+ttckbx5Ap3TRvjAAgqHY4UrgkRLiyvQppI8ULyPCc59GNimzco4pBXaMM8wEJ1yrJE6C4Vd6GflfjdUVhGpaji4oG+NBzVnBvA+bBfFnmwWsOiL/8kge+cFxqbW+XqLAAHz3aRV6WgB7wYGXP/0AYant1VKAHFLcnSzRtJqeKakW+rnbUf6eHDQWsF/7AhfG7PJ6qDS8zm8JMjWSZdb0WsOzr79A/IcL1tu4iyn2n9gKA6l9cOhPhYT3AEQJE4GCtLA9eEYILBTbKC4LWuxgnmo+G8VkAIsBoAy8dcSRBPXHZMKRZ5ssmpO766zOZqpdkcX0RcH2dwKUqZefwNrfhdoKy5rmi54/LU93YVYv/d/Mm8HyfV9sWkfEKvFHGM1v+PmCQJLh/CQvHtdu5fd6Had4L0arKa574XsUb07mwKau53Xn+iBBcDu.0CpRsu37FpDizsfXVCxOQ7iLBjJM6+72hczGl4+3RQ4=",
        "refreshTokenId": ""3ab11111-2222-33e4-a111-01a1b222cd3a"
    }
}

### validate authentication token
REQUEST
curl GET -H authorization:'AnaplanAuthToken {anaplan_auth_token}' https://auth.anaplan.com/token/validate

Response 200 (application/json)
{
    "meta": {
        "validationUrl": "https://auth.anaplan.com/token/validate"
    },
    "status": "SUCCESS",
    "statusMessage": "Token validated",
    "userInfo": {
        "userGuid": "8a89d9999f3c7099015f999d5208458a",
        "userId": "a.user@acme.com",
        "customerGuid": "8a80d99a5bf97b99995c3d1577610415"
    },
    "tokenInfo": {
        "expiresAt": 1509728252000
        "tokenId": "4d677e7d-c0ae-11e7-9f79-b179910b5099",
    }
}

## Schema References
The JSON responses include a `$schema` field with URLs containing the path segment `/objects/` 
(e.g. `https://example.com/objects/SomeResource`). Treat each unique `/objects/{Name}` as a 
named schema component and define it under `components/schemas`.

## Instructions
1. Infer request/response schemas from the sample JSON payloads
2. Map all `/objects/{Name}` schema URLs to `$ref: '#/components/schemas/{Name}'`
3. Document all path parameters, query parameters, and request bodies
4. Infer data types, required fields, and nullable fields from the samples
5. Use `allOf` / `oneOf` where polymorphism is evident
6. Add a `description` for every endpoint, parameter, and schema field you can infer
7. Flag any ambiguities as YAML comments (# TODO: ...)
8. Do NOT fabricate endpoints or fields not present in the docs or samples

Output only valid OpenAPI 3.0 JSON, starting with `openapi: "3.0.0"`.
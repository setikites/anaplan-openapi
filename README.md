You are an expert at writing OpenAPI 3.0 specifications.

I need you to generate a complete OpenAPI 3.0 JSON spec for a REST API based on the following inputs:

## API Documentation
[PASTE APIARY DOCUMENTATION HERE]

## Sample JSON Responses
[PASTE SAMPLE RESPONSES HERE]

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
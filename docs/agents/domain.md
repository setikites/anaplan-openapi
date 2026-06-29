# Domain Docs

This project has a **single-context** structure.

## Layout

```
/
├── CONTEXT.md                    (API glossary and landscape)
├── docs/adr/                     (architectural decisions)
│   ├── 0001-document-apis-as-is.md
│   ├── 0002-canonical-element-ordering.md
│   ├── 0003-description-standards.md
│   ├── 0004-id-source-path-descriptions.md
│   └── 0005-shared-parameter-components.md
└── [API folders]
    └── [API-specific READMEs]
```

## What skills read here

- `improve-codebase-architecture` — reads CONTEXT.md to learn API terminology and patterns
- `diagnose` — reads CONTEXT.md for domain language when debugging issues
- `tdd` — reads CONTEXT.md to understand the domain
- `grill-with-docs` — reads CONTEXT.md and docs/adr/ to challenge plans

## CONTEXT.md structure

[CONTEXT.md](../../CONTEXT.md) documents:
- The Anaplan APIs, their purpose, and key characteristics
- Authentication variations across APIs
- Data sources (Postman, Apiary, extracted schemas) and confidence levels for each API
- Key patterns and variations (pagination, error handling, etc.)

## docs/adr/ structure

[docs/adr/](../../docs/adr/) contains architectural decision records explaining the "why" behind major decisions:
- `0001-document-apis-as-is.md` — Why we document each API's actual patterns rather than normalizing them
- `0002-canonical-element-ordering.md` — Canonical ordering of OpenAPI elements
- `0003-description-standards.md` — Description writing standards
- `0004-id-source-path-descriptions.md` — Documenting ID sources in path parameter descriptions
- `0005-shared-parameter-components.md` — Shared parameter components

## Adding new context

When new terminology or decisions emerge:
1. Update CONTEXT.md with new terms or patterns
2. Create a new ADR in docs/adr/ if the decision is hard-to-reverse, surprising, or involves trade-offs

See [CONTEXT.md](../../CONTEXT.md) for format.

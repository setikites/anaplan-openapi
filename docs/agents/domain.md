# Domain Docs

This project has a **single-context** structure.

## Layout

```
/
├── CONTEXT.md                    (API glossary and landscape)
├── docs/adr/                     (architectural decisions)
│   └── 0001-document-apis-as-is.md
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
- The 9 Anaplan APIs, their purpose, and key characteristics
- Authentication variations across APIs
- Data sources (Postman, Apiary, extracted schemas) and confidence levels for each API
- Key patterns and variations (pagination, error handling, etc.)

## docs/adr/ structure

[docs/adr/](../../docs/adr/) contains architectural decision records explaining the "why" behind major decisions:
- `0001-document-apis-as-is.md` — Why we document each API's actual patterns rather than normalizing them

## Adding new context

When new terminology or decisions emerge:
1. Update CONTEXT.md with new terms or patterns
2. Create a new ADR in docs/adr/ if the decision is hard-to-reverse, surprising, or involves trade-offs

See [CONTEXT.md](../../CONTEXT.md) for format.

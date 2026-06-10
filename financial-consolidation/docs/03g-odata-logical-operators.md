# OData Logical Operators

Source: https://help.anaplan.com/logical-operators-f887fdbe-2896-48d1-8fbb-30a892f42722

All operators are used within the `$filter` query parameter.

## Comparison Operators

| Operator | Syntax             | Purpose                       | Example                        |
|----------|--------------------|-------------------------------|--------------------------------|
| `eq`     | `field eq value`   | Equals                        | `Date_Name eq '2024 Dec'`      |
| `ne`     | `field ne value`   | Not equals                    |                                |
| `gt`     | `field gt value`   | Greater than                  |                                |
| `ge`     | `field ge value`   | Greater than or equal         |                                |
| `lt`     | `field lt value`   | Less than                     |                                |
| `le`     | `field le value`   | Less than or equal            |                                |

## Logical Operators

| Operator | Syntax                          | Example                                               |
|----------|---------------------------------|-------------------------------------------------------|
| `and`    | `cond and cond`                 | `(Entity_Name eq '120') and (Date_Name eq '2024 Dec')`|
| `or`     | `cond or cond`                  |                                                       |
| `not`    | `not operand`                   |                                                       |

## Collection / String Operators

| Operator       | Syntax                     | Purpose                   |
|----------------|----------------------------|---------------------------|
| `has`          | `field has value`          | Enumeration flag check    |
| `in`           | `field in (v1,v2)`         | Membership testing        |
| `startswith`   | `startswith(field,value)`  | String prefix match       |
| `endswith`     | `endswith(field,value)`    | String suffix match       |

Parentheses can be used to override default operator precedence.

# microjq

```text
##      ## ##########   ######## ########     ######       ######   ######  
####  ####     ##     ##         ##      ## ##      ##       ##   ##      ##
##  ##  ##     ##     ##         ########   ##      ##       ##   ##  ##  ##
##      ##     ##     ##         ##    ##   ##      ## ##    ##   ##    ##  
##      ## ##########   ######## ##      ##   ######     ####       ####  ##
```

**A minimal jq clone in Python — query JSON from the command line, zero dependencies.**

Filter, map, and extract JSON with path expressions. Pipe-friendly, helpful error messages, and a clear comparison to the real jq. For quick JSON lookups when you don't want to install the full jq binary or deal with its complexity.

[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

```bash
$ microjq '.users[].name' <<< '{"users":[{"name":"Alice","age":30},{"name":"Bob","age":25}]}'
Alice
Bob

$ microjq '.[]|select(.age>25)' <<< '{"users":[{"name":"Alice","age":30},{"name":"Bob","age":25}]}'
{"name": "Alice", "age": 30}

$ microjq '.store.book[].price' <<< '{"store":{"book":[{"price":10},{"price":20},{"price":15}]}}'
[10, 20, 15]
```

*Real output from microjq — field extraction, filtering, and array projection.*

## Quickstart

```bash
pip install -e .
```

```bash
# Extract a field
microjq '.name' <<< '{"name":"Alice","age":30}'
# Alice

# Array element
microjq '.users[0].name' <<< '{"users":[{"name":"Alice"},{"name":"Bob"}]}'
# Alice

# All array elements
microjq '.users[].name' <<< '{"users":[{"name":"Alice"},{"name":"Bob"}]}'
# Alice
# Bob

# Read from file
microjq '.store.book[].price' data.json
```

## What it does

microjq parses JSON path expressions and evaluates them against JSON data. It handles field access, array indexing, iteration, piping, and a handful of built-in functions — enough for most everyday JSON querying tasks.

### Supported expressions

| Expression | Meaning | Example |
|-----------|---------|---------|
| `.foo` | Field access | `.name` → "Alice" |
| `.foo.bar` | Nested field | `.user.address.city` |
| `.[0]` | Array index | `.[0]` → first element |
| `.[]` | All array elements | `.[]` → each item |
| `.foo[]` | Field then iterate | `.users[].name` |
| `..` | Recursive descent | `.. | .name` → all names anywhere |
| `\|` | Pipe | `.users \| length` |
| `keys` | Object keys | `keys` → `["a","b","c"]` |
| `length` | Array/object length | `[1,2,3] \| length` → `3` |
| `sort` | Sort array | `[3,1,2] \| sort` → `[1,2,3]` |
| `unique` | Deduplicate | `[1,2,2,3] \| unique` → `[1,2,3]` |
| `reverse` | Reverse array | `[1,2,3] \| reverse` → `[3,2,1]` |
| `tostring` | To string | `42 \| tostring` → `"42"` |
| `tonumber` | To number | `"42" \| tonumber` → `42.0` |
| `join(str)` | Join array | `[1,2] \| join(", ")` → `"1, 2"` |
| `ascii_upcase` / `ascii_downcase` | Case | `"hello" \| ascii_upcase` → `"HELLO"` |
| `== != < > <= >=` | Comparisons | `.age > 25` |
| `select(expr)` | Filter | `.[] \| select(.age > 25)` |

### How it compares to jq

```
microjq '.foo.bar'          ~  jq '.foo.bar'
microjq '.[0]'               ~  jq '.[0]'
microjq '.[]'                ~  jq '.[]'
microjq '.foo[]'             ~  jq '.foo[]'
microjq 'keys'               ~  jq 'keys'
microjq 'length'             ~  jq 'length'
microjq 'sort'               ~  jq 'sort'
microjq 'unique'              ~  jq 'unique'
microjq 'reverse'            ~  jq 'reverse'
microjq 'tostring'           ~  jq 'tostring'
microjq '..'                 ~  jq '..'
microjq '.[]|select(.x==1)'  ~  jq '.[]|select(.x==1)'
```

### Limitations vs full jq

- No regex filters
- No variable bindings (`as $x`)
- No string interpolation
- No object/array construction (`{foo: .bar}`)
- No function definitions
- No streaming/lazy evaluation
- Single-file core — not optimized for very large JSON

## Installation

```bash
git clone https://github.com/yourusername/microjq.git
cd microjq
pip install -e .
```

Requires Python 3.9+. No external dependencies — uses only the standard library.

## Usage

### Command line

```bash
# Read from stdin
echo '{"name":"Alice","age":30}' | microjq '.name'
# Alice

# Read from file
microjq '.users[].name' data.json

# Raw output (no quotes on strings)
microjq --raw '.name' <<< '{"name":"Alice"}'
# Alice

# JSON lines mode (one object per line)
microjq --split '.name' records.jsonl

# Slurp mode (read all inputs into an array)
microjq --slurp '.[]' files.json

# Sort object keys in output
microjq --sort-keys '.users' data.json
```

### Programmatic use

```python
from microjq import jq, extract, parse_expr

# Query Python data directly
data = {"users": [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]}
names = jq(".users[].name", data)
print(names)  # ['Alice', 'Bob']

# Query JSON string
result = extract(".store.book[].price",
    '{"store":{"book":[{"price":10},{"price":20}]}}')
print(result)  # [10, 20]

# Parse once, evaluate many times
expr = parse_expr(".users[].name")
for user_record in many_records:
    print(expr.eval(user_record))
```

## Project structure

```
microjq/
├── __init__.py   # Public API: jq, extract, parse_expr, JQError
└── core.py       # Tokenizer, parser, AST, evaluator, built-in functions
```

Single-file core — the entire engine fits in `core.py` (~350 lines).

## Requirements

- Python 3.9+
- No external dependencies (stdlib only: `json`, `re`, `sys`, `pathlib`)

## License

MIT License — see [LICENSE](LICENSE).

"""CLI for microjq: query JSON from the command line, a jq clone."""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

from .core import jq, extract, JQError, parse_expr


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="microjq",
        description="A minimal jq clone in Python -- query JSON with simple path expressions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  microjq '.name' <<< '{"name":"Alice","age":30}'
  microjq '.users[].name' file.json
  microjq '.store.book[*].price' data.json
  microjq '.items | map(.price) | add' data.json
  microjq '.[] | select(.age > 25)' data.json
  microjq '.. | .name?' data.json            # recursive descent
  microjq 'keys' <<< '{"a":1,"b":2}'         # list keys
  microjq 'length' <<< '[1,2,3,4,5]'         # array length
  microjq '. | sort' <<< '[3,1,4,1,5]'       # sort array
  microjq '. | unique' <<< '[1,2,2,3,1]'     # unique values
  microjq '. | tostring' <<< 42              # convert to string

COMPARE TO jq:
  microjq '.foo.bar'   ~  jq '.foo.bar'
  microjq '.[0]'       ~  jq '.[0]'
  microjq '.[]'        ~  jq '.[]'
  microjq 'keys'       ~  jq 'keys'
  microjq 'length'     ~  jq 'length'
  microjq 'sort'       ~  jq 'sort'
  microjq 'unique'     ~  jq 'unique'
  microjq '..'         ~  jq '..'
  microjq '.[]|select(.x==1)' ~ jq '.[]|select(.x==1)'

LIMITATIONS vs full jq:
  - No complex regex filters
  - No variable bindings (as $x)
  - Limited to core functions above
  - String indexing not supported in brackets
""",
    )
    parser.add_argument("expression", help="jq expression (e.g. '.foo.bar', '.[] | select(.x > 5)')")
    parser.add_argument("file", nargs="?", default=None,
                        help="JSON file to read (reads stdin if omitted)")
    parser.add_argument("--raw", "-r", action="store_true",
                        help="Raw output (no quotes on strings)")
    parser.add_argument("--indent", "-i", type=int, default=2,
                        help="JSON output indentation (default: 2)")
    parser.add_argument("--split", "-s", action="store_true",
                        help="Read JSON lines (one object per line) instead of a single JSON value")
    parser.add_argument("--slurp", "-S", action="store_true",
                        help="Read all inputs into a single array")
    parser.add_argument("--sort-keys", action="store_true",
                        help="Sort object keys in output")

    args = parser.parse_args(argv)

    try:
        expr = args.expression
        ast = parse_expr(expr)
    except JQError as e:
        print(f"microjq: parse error: {e}", file=sys.stderr)
        return 1

    indent = args.indent
    raw = args.raw
    sort_keys = args.sort_keys

    def _emit(value: Any) -> None:
        if isinstance(value, str) and raw:
            print(value)
        elif isinstance(value, list):
            print(json.dumps(value, indent=indent, sort_keys=sort_keys))
        elif isinstance(value, dict):
            print(json.dumps(value, indent=indent, sort_keys=sort_keys))
        else:
            if raw and isinstance(value, str):
                print(value)
            else:
                print(json.dumps(value, indent=indent, sort_keys=sort_keys))

    def _process(data: Any) -> None:
        try:
            results = list(ast.eval(data))
        except JQError as e:
            print(f"microjq: runtime error: {e}", file=sys.stderr)
            return 1
        if not results:
            print("(no results)", file=sys.stderr)
            return 0
        for r in results:
            _emit(r)
        return 0

    if args.slurp:
        items: list[Any] = []
        if args.file:
            _load_file(args.file, items, split=args.split)
        else:
            _load_stdin(items, split=args.split)
        for item in _process([items]):
            pass
        return 0

    elif args.file:
        if args.split:
            _process_jsonl(args.file, ast, raw, indent, sort_keys)
            return 0
        else:
            data = _load_json_file(args.file)
            return _process(data)

    else:
        if args.split:
            _process_jsonl_stdin(ast, raw, indent, sort_keys)
            return 0
        else:
            data = _load_stdin_json()
            return _process(data)


def _load_json_file(path: str) -> Any:
    p = Path(path)
    try:
        return json.loads(p.read_text())
    except FileNotFoundError:
        print(f"microjq: file not found: {path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"microjq: invalid JSON in {path}: {e}", file=sys.stderr)
        sys.exit(1)


def _load_stdin_json() -> Any:
    try:
        text = sys.stdin.read()
        if not text.strip():
            return None
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"microjq: invalid JSON on stdin: {e}", file=sys.stderr)
        sys.exit(1)


def _load_file(path: str, items: list, split: bool = False) -> None:
    p = Path(path)
    try:
        if split:
            for line in p.read_text().splitlines():
                line = line.strip()
                if line:
                    items.append(json.loads(line))
        else:
            items.append(json.loads(p.read_text()))
    except FileNotFoundError:
        print(f"microjq: file not found: {path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"microjq: invalid JSON in {path}: {e}", file=sys.stderr)
        sys.exit(1)


def _load_stdin(items: list, split: bool = False) -> None:
    try:
        text = sys.stdin.read()
        if not text.strip():
            return
        if split:
            for line in text.splitlines():
                line = line.strip()
                if line:
                    items.append(json.loads(line))
        else:
            items.append(json.loads(text))
    except json.JSONDecodeError as e:
        print(f"microjq: invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)


def _process_jsonl(path: str, ast: "ASTNode", raw: bool, indent: int, sort_keys: bool) -> int:
    p = Path(path)
    rc = 0
    for line_num, line in enumerate(p.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as e:
            print(f"microjq: invalid JSON on line {line_num}: {e}", file=sys.stderr)
            rc = 1
            continue
        try:
            results = list(ast.eval(data))
        except JQError as e:
            print(f"microjq: error on line {line_num}: {e}", file=sys.stderr)
            rc = 1
            continue
        if not results:
            continue
        for r in results:
            if isinstance(r, str) and raw:
                print(r)
            else:
                print(json.dumps(r, indent=indent, sort_keys=sort_keys))
    return rc


def _process_jsonl_stdin(ast: "ASTNode", raw: bool, indent: int, sort_keys: bool) -> int:
    rc = 0
    for line_num, line in enumerate(sys.stdin, 1):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as e:
            print(f"microjq: invalid JSON on line {line_num}: {e}", file=sys.stderr)
            rc = 1
            continue
        try:
            results = list(ast.eval(data))
        except JQError as e:
            print(f"microjq: error on line {line_num}: {e}", file=sys.stderr)
            rc = 1
            continue
        if not results:
            continue
        for r in results:
            if isinstance(r, str) and raw:
                print(r)
            else:
                print(json.dumps(r, indent=indent, sort_keys=sort_keys))
    return rc


if __name__ == "__main__":
    sys.exit(main())

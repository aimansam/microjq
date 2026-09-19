"""microjq -- Minimal jq clone: query JSON with a simple path expression."""

from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Any, Callable, Iterator


class JQError(Exception):
    pass


# ── Tokenizer ────────────────────────────────────────────────────────

TOKEN_RE: re.Pattern[str] | None = None

def _ensure_tokenizer():
    global TOKEN_RE
    if TOKEN_RE is not None:
        return
    import re
    TOKEN_RE = re.compile(
        r"""(?P<IDENT>[a-zA-Z_][a-zA-Z0-9_]*)|(?P<NUM>-?\d+(?:\.\d+)?)|"""
        r"""(?P<STR>"(?:\\\.|[^"\\])*")|(?P<BOOL>true|false|null)|"""
        r"""(?P<SLASH>/)|(?P<LBRACK>\[)|(?P<RBRACK>\])|"""
        r"""(?P<LPAREN>\()|(?P<RPAREN>\))|(?P<COMMA>,)|"""
        r"""(?P<PIPE>\|)|(?P<DOT>\.)|(?P<STAR>\*)|"""
        r"""(?P<EQ>==|!=|<=|>=|<|>)|(?P<SKIP>\s+)|(?P<OTHER>.)""",
        re.VERBOSE,
    )


def tokenize(expr: str) -> list[tuple[str, str]]:
    _ensure_tokenizer()
    tokens = []
    pos = 0
    while pos < len(expr):
        m = TOKEN_RE.match(expr, pos)
        if not m:
            raise JQError(f"Unexpected char at pos {pos}: {expr[pos]!r}")
        kind = m.lastgroup
        text = m.group()
        if kind == "SKIP":
            pos = m.end()
            continue
        tokens.append((kind, text))
        pos = m.end()
    return tokens


# ── AST ──────────────────────────────────────────────────────────────

class Node:
    def eval(self, val: Any) -> Iterator[Any]:
        yield val


class Identity(Node):
    pass


class Literal(Node):
    def __init__(self, v: Any):
        self.v = v
    def eval(self, val):
        yield self.v


class Field(Node):
    def __init__(self, name: str):
        self.name = name
    def eval(self, val):
        if isinstance(val, dict) and self.name in val:
            yield val[self.name]


class Index(Node):
    def __init__(self, key: Node):
        self.key = key
    def eval(self, val):
        for k in self.key.eval(val):
            if isinstance(val, dict):
                sk = str(k)
                if sk in val:
                    yield val[sk]
            elif isinstance(val, list):
                try:
                    idx = int(k)
                    if 0 <= idx < len(val):
                        yield val[idx]
                    elif idx < 0:
                        yield val[len(val) + idx]
                except (ValueError, TypeError):
                    pass


class Pipe(Node):
    def __init__(self, l: Node, r: Node):
        self.l, self.r = l, r
    def eval(self, val):
        for v in self.l.eval(val):
            yield from self.r.eval(v)


class Recurse(Node):
    def __init__(self, child: Node = None):
        self.child = child
    def eval(self, val):
        yield val
        if isinstance(val, dict):
            for item in val.values():
                yield from self.eval(item)
        elif isinstance(val, list):
            for item in val:
                yield from self.eval(item)


class Call(Node):
    def __init__(self, func: Callable, args: list[Node]):
        self.func, self.args = func, args
    def eval(self, val):
        av = []
        for a in self.args:
            r = list(a.eval(val))
            av.append(r[0] if r else None)
        try:
            res = self.func(val, *av)
            if isinstance(res, list):
                yield from res
            else:
                yield res
        except (TypeError, KeyError, IndexError) as e:
            raise JQError(f"{self.func.__name__}: {e}")


class Comparator(Node):
    def __init__(self, l: Node, op: str, r: Node):
        self.l, self.op, self.r = l, op, r
    def eval(self, val):
        for lv in self.l.eval(val):
            for rv in self.r.eval(val):
                try:
                    if self.op == "==": yield lv == rv
                    elif self.op == "!=": yield lv != rv
                    elif self.op == "<": yield lv < rv
                    elif self.op == ">": yield lv > rv
                    elif self.op == "<=": yield lv <= rv
                    elif self.op == ">=": yield lv >= rv
                except TypeError:
                    yield False


# ── Built-ins ────────────────────────────────────────────────────────

def _keys(v, *a): return list(v.keys()) if isinstance(v, dict) else []
def _len(v, *a): return len(v) if isinstance(v, (dict, list, str)) else 0
def _sort(v, *a):
    if isinstance(v, list):
        return sorted(v, key=str)
    return [v]
def _uniq(v, *a):
    if isinstance(v, list):
        seen = []
        for x in v:
            if x not in seen: seen.append(x)
        return seen
    return [v]
def _rev(v, *a): return list(reversed(v)) if isinstance(v, list) else [v]
def _ts(v, *a): return json.dumps(v)
def _tn(v, *a):
    try: return float(v)
    except: return 0.0
def _join(v, *a):
    if isinstance(v, list):
        sep = a[0] if a and a[0] else ", "
        return sep.join(json.dumps(i) for i in v)
    return json.dumps(v)
def _down(v, *a): return str(v).lower()
def _up(v, *a): return str(v).upper()

_FUNCS: dict[str, Callable] = {
    "keys": _keys, "length": _len, "sort": _sort, "unique": _uniq,
    "reverse": _rev, "tostring": _ts, "tonumber": _tn,
    "join": _join, "ascii_downcase": _down, "ascii_upcase": _up,
}


# ── Parser (recursive descent) ──────────────────────────────────────

class Parser:
    def __init__(self, tokens: list[tuple[str, str]]):
        self.t = tokens
        self.p = 0

    def peek(self) -> tuple[str, str] | None:
        return self.t[self.p] if self.p < len(self.t) else None

    def eat(self, kind: str | None = None) -> tuple[str, str]:
        tok = self.peek()
        if tok is None:
            raise JQError("Unexpected end")
        if kind and tok[0] != kind:
            raise JQError(f"Expected {kind}, got {tok[0]}")
        self.p += 1
        return tok

    def parse(self) -> Node:
        return self.pipe()

    def pipe(self) -> Node:
        left = self.path()
        while self.peek() and self.peek()[1] == "|":
            self.eat("PIPE")
            right = self.path()
            left = Pipe(left, right)
        return left

    def path(self) -> Node:
        """Chain of steps: Identity → .foo → .bar → [0]"""
        node = Identity()
        while self.peek():
            t = self.peek()
            if t[1] in ("|", ")", "]"):
                break
            node = self.step(node)
        return node

    def step(self, left: Node) -> Node:
        t = self.peek()
        if t is None:
            return left

        # .field
        if t[1] == ".":
            self.eat("DOT")
            nt = self.peek()
            if nt is None or nt[1] in ("|", ")", "]", "/", "."):
                return left
            if nt[0] == "IDENT":
                return Pipe(left, Field(self.eat("IDENT")[1]))
            if nt[0] == "STR":
                self.eat("STR")
                return Pipe(left, Field(json.loads(nt[1])))
            if nt[1] == "*":
                self.eat("STAR")
                return Recurse(left)
            if nt[1] == "[":
                return self.bracket(left)
            raise JQError(f"Bad after dot: {nt}")

        # /  — recursive descent
        if t[1] == "/":
            self.eat("SLASH")
            return Recurse(left)

        # [index]
        if t[0] == "LBRACK":
            return self.bracket(left)

        # bare ident → .field or function call
        if t[0] == "IDENT":
            name = self.eat("IDENT")[1]
            if self.peek() and self.peek()[0] == "LPAREN":
                return self.call(name)
            # Known built-in function without parens: keys, length, sort, etc.
            if name in _FUNCS:
                return Pipe(left, Call(_FUNCS[name], []))
            return Pipe(left, Field(name))

        # (expr)
        if t[1] == "(":
            self.eat("LPAREN")
            inner = self.parse()
            self.eat("RPAREN")
            return Pipe(left, inner)

        # literal
        if t[0] == "NUM":
            self.eat("NUM")
            return Pipe(left, Literal(float(t[1]) if "." in t[1] else int(t[1])))
        if t[0] == "STR":
            self.eat("STR")
            return Pipe(left, Literal(json.loads(t[1])))
        if t[0] == "BOOL":
            self.eat("BOOL")
            return Pipe(left, Literal(json.loads(t[1])))

        raise JQError(f"Unexpected: {t}")

    def bracket(self, left: Node) -> Node:
        self.eat("LBRACK")
        if self.peek() and self.peek()[0] == "RBRACK":
            self.eat("RBRACK")
            return Pipe(left, Recurse())
        parts: list[Node] = []
        parts.append(self.path())
        while self.peek() and self.peek()[0] == "COMMA":
            self.eat("COMMA")
            parts.append(self.path())
        self.eat("RBRACK")
        inner: Node
        if len(parts) == 1:
            inner = Index(parts[0])
        else:
            inner = MultiIdx(parts)
        return Pipe(left, inner)

    def call(self, name: str) -> Node:
        self.eat("LPAREN")
        args: list[Node] = []
        if self.peek() and self.peek()[0] != "RPAREN":
            args.append(self.path())
            while self.peek() and self.peek()[0] == "COMMA":
                self.eat("COMMA")
                args.append(self.path())
        self.eat("RPAREN")
        f = _FUNCS.get(name)
        if f is None:
            raise JQError(f"Unknown function: {name}")
        return Pipe(self._dummy_left(), Call(f, args))

    def _dummy_left(self) -> Node:
        """Return a left node that yields the current input for function calls."""
        return _CallLeft()


class _CallLeft(Node):
    """Identity node used as left for bare function calls like `keys`."""
    def eval(self, val):
        yield val


class MultiIndex(Node):
    """[a, b, c] — yield items at each index from current value."""
    def __init__(self, parts: list[Node]):
        self.parts = parts
    def eval(self, val):
        for part in self.parts:
            yield from Index(part).eval(val)


# ── Public API ───────────────────────────────────────────────────────

def parse_expr(expr: str) -> Node:
    return Parser(tokenize(expr)).parse()


def jq(expr: str, data: Any) -> list[Any]:
    return list(parse_expr(expr).eval(data))


def extract(expr: str, src: str | Path) -> list[Any]:
    if isinstance(src, Path) or (isinstance(src, str) and "." in src and "\n" not in src):
        data = json.loads(Path(src).read_text())
    else:
        data = json.loads(src)
    return jq(expr, data)

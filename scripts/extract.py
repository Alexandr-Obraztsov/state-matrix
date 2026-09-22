#!/usr/bin/env python3
"""Кандидаты в параметры. Извлекает С ЗАПАСОМ: лишний кандидат безвреден,
пропущенный — нет. Модель обязана учесть каждого: параметром или в excluded."""
import re, sys, json, os, argparse

PAT = [
    # (вид, регулярка, группа с именем)
    ("state",    r"\bconst\s*\[\s*(\w+)\s*,\s*set\w+\s*\]\s*=\s*useState", 1),
    ("reducer",  r"\bconst\s*\[\s*(\w+)\s*,\s*\w+\s*\]\s*=\s*useReducer", 1),
    ("ref",      r"\bconst\s+(\w+)\s*=\s*useRef", 1),
    ("memo",     r"\bconst\s+(\w+)\s*=\s*useMemo", 1),
    ("context",  r"\bconst\s+\{?\s*([\w,\s]+?)\s*\}?\s*=\s*useContext", 1),
    ("endpoint", r"\b(?:fetch|axios\.\w+)\(\s*[`'\"]([^`'\"]+)", 1),
    ("query",    r"\bconst\s*\{?\s*([\w,\s]+?)\s*\}?\s*=\s*use(?:Query|SWR|Fetch|\w*Request)\b", 1),
    ("env",      r"\b(?:matchMedia|navigator\.(\w+)|window\.__\w+__)", 0),
]
PROPS_BLOCK = r"(?:interface|type)\s+\w*Props\w*\s*=?\s*\{([^}]*)\}"
DESTRUCTURE = r"export\s+(?:default\s+)?function\s+\w+\s*\(\s*\{([^}]*)\}"
BRANCH = r"(\?\s*\()|(&&\s*[<(])|(\bif\s*\()|(\bswitch\s*\()"


def scan(path):
    src = open(path, encoding="utf-8").read()
    lines = src.split("\n")
    out = []

    def add(kind, name, idx):
        name = name.strip()
        if not name or not re.fullmatch(r"\w+", name):
            return
        out.append({"kind": kind, "name": name, "line": idx + 1,
                    "text": lines[idx].strip()[:110]})

    for kind, pat, g in PAT:
        for m in re.finditer(pat, src):
            idx = src[:m.start()].count("\n")
            raw = m.group(g) if g and m.lastindex and m.group(g) else m.group(0)
            for part in re.split(r"[,\s]+", raw):
                add(kind, part, idx)

    for pat in (PROPS_BLOCK, DESTRUCTURE):
        for m in re.finditer(pat, src, re.S):
            idx = src[:m.start()].count("\n")
            for row in m.group(1).split("\n"):
                nm = re.match(r"\s*(\w+)\s*[?:,]", row) or re.match(r"\s*(\w+)\s*,?\s*$", row)
                if nm:
                    add("prop", nm.group(1), idx + m.group(1)[:m.group(1).find(row)].count("\n"))

    branches = len(re.findall(BRANCH, src))
    seen, uniq = set(), []
    for c in out:
        k = (c["kind"], c["name"])
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    return uniq, branches, len(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    cands, branches, nlines = scan(a.target)
    if a.json:
        print(json.dumps({"target": a.target, "candidates": cands,
                          "branches": branches, "lines": nlines},
                         ensure_ascii=False, indent=2))
        return
    print(f"# {a.target}  ({nlines} строк, ветвлений в разметке: {branches})")
    print(f"# кандидатов: {len(cands)} — КАЖДЫЙ обязан попасть в модель или в excluded\n")
    w = max((len(c["name"]) for c in cands), default=8)
    for c in cands:
        print(f"  {c['kind']:9} {c['name']:{w}}  :{c['line']:<4} {c['text']}")


if __name__ == "__main__":
    main()

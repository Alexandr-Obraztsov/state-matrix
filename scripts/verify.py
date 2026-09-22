#!/usr/bin/env python3
"""Проверяет ссылки модели: файл существует, строка существует, на ней (±2)
упомянут параметр или раздел. Ловит выдуманные цитаты."""
import os, re, sys, argparse
import store

REF = re.compile(r"(?:^|[\s(])((?:[\w./-]+\.\w+)?):(\d+)")
# ссылка на раздел спеки: docs/checkout.md:§2  или  docs/checkout.md:"Лимиты"
SEC = re.compile(r"([\w./-]+\.\w+):(§[\w.\-]+|\"[^\"]+\")")


def resolve(ref_file, source, root):
    base = os.path.join(root, source)
    if not ref_file:
        return base
    if os.path.isabs(ref_file):
        return ref_file
    cand = os.path.join(os.path.dirname(base), os.path.basename(ref_file))
    return cand if os.path.exists(cand) else os.path.join(root, ref_file)


def check_section(text, source, root):
    """Ссылка на раздел документа: раздел обязан в нём существовать."""
    m = SEC.search(str(text))
    if not m:
        return None
    path = resolve(m.group(1), source, root)
    if not os.path.exists(path):
        return "bad", f"нет файла {path}"
    body = open(path, encoding="utf-8").read()
    needle = m.group(2).strip('"')
    if needle not in body:
        return "bad", (f"{os.path.basename(path)}: раздела «{needle}» в документе нет"
                       " — ссылка выдумана")
    return "ok", f"{os.path.basename(path)}:{needle}"


def check_ref(text, token, source, root):
    """-> (статус, сообщение)"""
    sec = check_section(text, source, root)
    if sec:
        return sec
    m = REF.search(str(text))
    if not m:
        return "unverifiable", "нет ссылки вида file:line"
    path = resolve(m.group(1), source, root)
    if not os.path.exists(path):
        return "bad", f"нет файла {path}"
    lines = open(path, encoding="utf-8").read().split("\n")
    n = int(m.group(2))
    if not (1 <= n <= len(lines)):
        return "bad", f"{os.path.basename(path)}: строки {n} не существует (всего {len(lines)})"
    window = "\n".join(lines[max(0, n - 3):n + 2]).lower()
    if token and token.lower() not in window:
        return "suspect", (f"{os.path.basename(path)}:{n} — «{token}» не упомянут "
                           f"в строках {max(1,n-2)}–{n+2}")
    return "ok", f"{os.path.basename(path)}:{n}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    m = store.load(a.model)
    src = m.get("source", "")
    errs, susp, unv, ok = [], [], [], 0

    for n, p in (m.get("params") or {}).items():
        st, msg = check_ref(p.get("from", ""), n, src, a.root)
        {"bad": errs, "suspect": susp, "unverifiable": unv}.get(st, []).append(f"params.{n}: {msg}")
        ok += st == "ok"
    for i, c in enumerate(m.get("constraints") or []):
        st, msg = check_ref(c.get("evidence", ""), None, src, a.root)
        {"bad": errs, "suspect": susp, "unverifiable": unv}.get(st, []).append(
            f"constraints[{i}] ({c.get('id','?')}): {msg}")
        ok += st == "ok"
    for i, t in enumerate(m.get("transitions") or []):
        st, msg = check_ref(t.get("evidence", ""), None, src, a.root)
        {"bad": errs, "suspect": susp, "unverifiable": unv}.get(st, []).append(
            f"transitions[{i}] «{t.get('event')}»: {msg}")
        ok += st == "ok"
    for i, o in enumerate(m.get("outcomes") or []):
        st, msg = check_ref(o.get("evidence", ""), None, src, a.root)
        {"bad": errs, "suspect": susp, "unverifiable": unv}.get(st, []).append(
            f"outcomes[{i}]: {msg}")
        ok += st == "ok"

    print(f"{a.model}")
    print(f"  ссылок подтверждено: {ok}")
    for x in errs: print("  ERROR    " + x)
    for x in susp: print("  SUSPECT  " + x)
    if unv:
        print(f"  без ссылки: {len(unv)}")
        for x in unv[:20]: print("  no-ref   " + x)
    sys.exit(1 if errs or susp else 0)


if __name__ == "__main__":
    main()

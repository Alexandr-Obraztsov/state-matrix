#!/usr/bin/env python3
"""Проверяет ссылки модели: файл существует, строка существует, на ней (±2)
упомянут параметр. Ловит выдуманные цитаты. Плюс покрытие кандидатов extract.py."""
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


def coverage(model, target, root):
    """Каждый кандидат extract.py обязан быть параметром или в excluded."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import extract
    path = target if os.path.isabs(target) else os.path.join(root, target)
    if not os.path.exists(path):
        return [f"цель {path} не найдена — покрытие не проверено"], 0
    cands, _, _ = extract.scan(path)
    known = set(model.get("params") or {}) | set(model.get("excluded") or {})
    miss = [c for c in cands if c["name"] not in known]
    return ([f"кандидат «{c['name']}» ({c['kind']}, :{c['line']}) не учтён: "
             "ни параметр, ни excluded" for c in miss], len(cands))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--root", default=".")
    ap.add_argument("--target", help="файл для проверки покрытия (по умолчанию source модели)")
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

    cov_errs, ncand = coverage(m, a.target or src, a.root)
    errs += cov_errs

    print(f"{a.model}")
    print(f"  ссылок подтверждено: {ok}   кандидатов проверено: {ncand}")
    for x in errs: print("  ERROR    " + x)
    for x in susp: print("  SUSPECT  " + x)
    if unv:
        print(f"  без ссылки: {len(unv)}")
        for x in unv[:20]: print("  no-ref   " + x)
    sys.exit(1 if errs or susp else 0)


if __name__ == "__main__":
    main()

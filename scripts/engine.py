#!/usr/bin/env python3
"""Модель → матрица. Детерминирован: одна модель даёт побайтово одинаковый вывод.

Состояния к строкам не привязываются условиями — они назначаются вручную
после свёртки и хранятся в модели по ключу строки.
"""
import sys, os, json, itertools, hashlib, datetime, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store
from store import CEILING


def as_list(v):
    return v if isinstance(v, list) else [v]


def matches(row, cond):
    for k, v in (cond or {}).items():
        if k not in row or row[k] not in as_list(v):
            return False
    return True


def row_key(values, names):
    """Ключ строки — переживает пересборку, по нему хранится назначенное состояние."""
    return "|".join(f"{n}={values[n]}" for n in names)


def rule_text(c):
    def vals(v):
        return " или ".join(f"«{x}»" for x in as_list(v))
    if "forbid" in c:
        cond = ", ".join(f"{k} = {vals(v)}" for k, v in c["forbid"].items())
        return {"kind": "запрет", "what": f"комбинация {cond} невозможна"}
    cond = ", ".join(f"{k} = {vals(v)}" for k, v in (c.get("when") or {}).items()) or "всегда"
    ps = ", ".join(c["irrelevant"])
    return {"kind": "схлопывание", "what": f"при {cond} значения {ps} на исход не влияют"}


def build(model):
    params = model["params"]
    names = list(params)
    axes = [params[n]["values"] for n in names]
    total = 1
    for a in axes:
        total *= len(a)
    rows = [dict(zip(names, c)) for c in itertools.product(*axes)]

    cons = list(model.get("constraints") or [])
    forbids = [c for c in cons if "forbid" in c]
    irrel = [c for c in cons if "irrelevant" in c]

    valid, removed = rows, {}
    for c in forbids:
        before = len(valid)
        valid = [r for r in valid if not matches(r, c["forbid"])]
        removed[c.get("id")] = before - len(valid)

    groups, order, why = {}, [], {}
    for r in valid:
        v, used = dict(r), []
        for c in irrel:
            if matches(r, c.get("when") or {}):
                for p in c["irrelevant"]:
                    if v[p] != "*":
                        v[p] = "*"
                        used.append(c)
        k = row_key(v, names)
        if k not in groups:
            groups[k] = {"values": v, "covered": 0}
            order.append(k)
            why[k] = {id(c): c for c in used}
        groups[k]["covered"] += 1

    assigned = model.get("assignments") or {}
    by_name = {s["name"]: s for s in (model.get("states") or [])}
    matrix = []
    for i, k in enumerate(order):
        g = groups[k]
        name = assigned.get(k)
        matrix.append({
            "id": f"r{i:03d}",
            "key": k,
            "values": g["values"],
            "covers": g["covered"],
            "state": name if name in by_name else None,
            "desc": (by_name.get(name) or {}).get("desc"),
        })

    specials = [{"param": n, "value": s}
                for n in names for s in (params[n].get("special") or [])]
    state_stats = [{"name": s["name"], "desc": s.get("desc"),
                    "evidence": s.get("evidence", "—"),
                    "rows": sum(1 for m in matrix if m["state"] == s["name"])}
                   for s in (model.get("states") or [])]
    no_state = [m["id"] for m in matrix if not m["state"]]

    findings = []
    if len(matrix) > CEILING:
        contrib = sorted(((len(p["values"]), n) for n, p in params.items()), reverse=True)
        lines = [f"{len(matrix)} строк при потолке {CEILING}", "", "вклад параметров:"]
        lines += [f"  {n:14} ×{f}" for f, n in contrib]
        lines += ["", "ищи правила свёртки в спеке; если их нет — это несколько систем "
                      "в одном документе, предложи разбиение"]
        findings.append({"class": "CEILING", "severity": "block",
                         "message": "\n".join(lines)})
    if no_state:
        findings.append({"class": "UNDEFINED", "severity": "warn",
                         "message": f"{len(no_state)} строк без состояния",
                         "rows": no_state})

    return {
        "system": model["system"],
        "source": model.get("source", "—"),
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "model_hash": hashlib.sha256(json.dumps(model, sort_keys=True, default=str)
                                     .encode()).hexdigest()[:12],
        "ceiling": CEILING,
        "params": params,
        "param_order": names,
        "excluded": model.get("excluded") or {},
        "rules": [dict(rule_text(c), id=c.get("id"), desc=c.get("desc"),
                       evidence=c.get("evidence", "—"),
                       removed=removed.get(c.get("id"))) for c in cons],
        "states": state_stats,
        "rows": matrix,
        "specials": specials,
        "findings": findings,
        "counts": {"total": total, "valid": len(valid), "collapsed": len(matrix),
                   "specials": len(specials), "no_state": len(no_state)},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("-o", "--out")
    a = ap.parse_args()
    res = build(store.load(a.model))
    if a.out:
        store.save(a.out, res)
        c = res["counts"]
        print(f"{res['system']}: {c['total']} → {c['valid']} → {c['collapsed']} строк "
              f"(+{c['specials']} спец), без состояния {c['no_state']}")
    else:
        print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

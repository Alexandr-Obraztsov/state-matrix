#!/usr/bin/env python3
"""Модель → матрица. Детерминирован: одна модель даёт побайтово одинаковый вывод."""
import sys, os, json, itertools, hashlib, datetime, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store
from store import CEILING


def as_list(v):
    return v if isinstance(v, list) else [v]


def matches(row, cond):
    """Строка подходит под условие, если совпали все указанные параметры."""
    for k, v in (cond or {}).items():
        if k not in row or row[k] not in as_list(v):
            return False
    return True


def rule_text(c):
    """Правило по-русски: что делает с матрицей."""
    def vals(v):
        return " или ".join(f"«{x}»" for x in as_list(v))
    if "forbid" in c:
        cond = ", ".join(f"{k} = {vals(v)}" for k, v in c["forbid"].items())
        return {"kind": "запрет", "what": f"комбинация {cond} невозможна",
                "effect": "строки вычёркиваются"}
    cond = ", ".join(f"{k} = {vals(v)}" for k, v in (c.get("when") or {}).items()) or "всегда"
    ps = ", ".join(c["irrelevant"])
    return {"kind": "схлопывание", "what": f"при {cond} значения {ps} на исход не влияют",
            "effect": f"колонки {ps} сливаются в «∗»"}


def state_of(row, states):
    """Первое подходящее состояние. Порядок в модели значим."""
    for st in states:
        if matches(row, st.get("when") or {}):
            return st
    return None


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

    # 1. запреты вычёркивают строки
    valid, funnel_rules = rows, []
    for c in forbids:
        before = len(valid)
        valid = [r for r in valid if not matches(r, c["forbid"])]
        funnel_rules.append({"id": c.get("id"), "removed": before - len(valid)})

    # 2. схлопывание незначащих колонок
    groups, order, why = {}, [], {}
    for r in valid:
        v, used = dict(r), []
        for c in irrel:
            if matches(r, c.get("when") or {}):
                for p in c["irrelevant"]:
                    if v[p] != "*":
                        v[p] = "*"
                        used.append(c)
        k = "|".join(f"{x}={v[x]}" for x in names)
        if k not in groups:
            groups[k] = {"values": v, "covered": []}
            order.append(k)
            why[k] = {id(c): c for c in used}
        groups[k]["covered"].append(r)

    states = model.get("states") or []
    matrix, mixed = [], []
    for i, k in enumerate(order):
        g = groups[k]
        starred = [p for p, x in g["values"].items() if x == "*"]
        hits = {(state_of(r, states) or {}).get("name") for r in g["covered"]}
        st = state_of(g["values"], states)
        if st is None and len(hits) == 1 and next(iter(hits)):
            st = next(x for x in states if x["name"] == next(iter(hits)))
        row = {
            "id": f"r{i:03d}",
            "values": g["values"],
            "covers": len(g["covered"]),
            "collapsed": {p: sorted({str(c[p]) for c in g["covered"]}) for p in starred},
            "rules": [{"what": rule_text(c)["what"], "evidence": c.get("evidence", "—")}
                      for c in why[k].values()],
            "state": (st or {}).get("name"),
            "desc": (st or {}).get("desc"),
        }
        if len(hits) > 1:
            mixed.append(row["id"])
        matrix.append(row)

    specials = [{"param": n, "value": s}
                for n in names for s in (params[n].get("special") or [])]

    state_stats = [{"name": st["name"], "desc": st.get("desc"),
                    "when": st.get("when") or {}, "evidence": st.get("evidence", "—"),
                    "rows": sum(1 for m in matrix if m["state"] == st["name"])}
                   for st in states]
    no_state = [m["id"] for m in matrix if not m["state"]]

    findings = []
    if len(matrix) > CEILING:
        contrib = sorted(((len(p["values"]), n) for n, p in params.items()), reverse=True)
        lines = [f"{len(matrix)} строк при потолке {CEILING}", "", "вклад параметров:"]
        lines += [f"  {n:14} ×{f}" for f, n in contrib]
        lines.append("")
        lines.append("ищи правила свёртки в спеке; если их нет — это несколько систем "
                     "в одном документе, предложи разбиение")
        findings.append({"class": "CEILING", "severity": "block",
                         "message": "\n".join(lines)})
    if mixed:
        findings.append({"class": "MIXED_STATE", "severity": "block",
                         "message": f"{len(mixed)} схлопнутых строк покрывают разные "
                                    "состояния — правило схлопывания слишком широкое",
                         "rows": mixed})
    for i in range(len(irrel)):
        for j in range(i + 1, len(irrel)):
            a, b = irrel[i], irrel[j]
            if not (a.get("when") and b.get("when")):
                continue
            n = sum(1 for r in valid
                    if matches(r, a["when"]) and matches(r, b["when"]))
            if n:
                findings.append({
                    "class": "RULE_OVERLAP", "severity": "block",
                    "message": f"правила {a.get('id')} и {b.get('id')} применимы "
                               f"одновременно к {n} комбинациям — порядок не определён"})
    if no_state:
        findings.append({"class": "UNDEFINED", "severity": "warn",
                         "message": f"{len(no_state)} строк не отнесены ни к одному состоянию",
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
                       removed=next((f["removed"] for f in funnel_rules
                                     if f["id"] == c.get("id")), None))
                  for c in cons],
        "states": state_stats,
        "no_state": len(no_state),
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
              f"(+{c['specials']} спец), находок {len(res['findings'])}")
    else:
        print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

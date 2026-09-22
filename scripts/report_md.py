#!/usr/bin/env python3
"""Отчёт в markdown для чата. Читает result.json — числа те же, что в HTML."""
import json, sys, argparse
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import store


def vals(v):
    return " / ".join(f"`{x}`" for x in (v if isinstance(v, list) else [v]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("result")
    ap.add_argument("--env", type=int, default=0)
    a = ap.parse_args()
    d = json.load(open(a.result))
    s = d["slices"][a.env]
    c = s["counts"]
    env = ", ".join(f"{k} = {v}" for k, v in s["env"].items()) or "единственное"
    P = d["params"]
    L = []

    L.append(f"# {d['system']}")
    L.append(f"`{d['source']}` · режим: {'спека' if d['mode']=='spec' else 'код'} "
             f"· окружение: {env}"
             + (f" (всего окружений {len(d['slices'])})" if len(d["slices"]) > 1 else ""))
    L.append("")

    L.append("## Параметры")
    L.append("")
    for n in d["param_order"] + d["env_order"]:
        p = P[n]
        tag = " · **окружение**" if p.get("env") else ""
        L.append(f"**`{n}`** — {p.get('type','—')}{tag}")
        if p.get("desc"):
            L.append(f"  {p['desc']}")
        L.append(f"  значения: {vals(p.get('values', []))}")
        if p.get("special"):
            L.append(f"  вне матрицы: {vals(p['special'])}")
        L.append(f"  источник: {p.get('from','—')}")
        L.append("")
    if d.get("excluded"):
        L.append("**Исключено из модели:**")
        L.append("")
        for k, v in d["excluded"].items():
            L.append(f"- `{k}` — {v}")
        L.append("")

    L.append("## Правила")
    L.append("")
    if not s["rules"]:
        L.append("_правил нет — матрица полная_")
    for r in s["rules"]:
        mark = "" if r["status"] == "proven" else " ⚠️ **не подтверждено**"
        L.append(f"**{r['kind'].capitalize()}**{mark} — {r['what']}")
        if r.get("desc"):
            L.append(f"  {r['desc']}")
        L.append(f"  {r['effect']}, затрагивает {r['rows']} комбинаций")
        L.append(f"  основание: {r['evidence']}")
        L.append("")

    if s.get("initial"):
        L.append("## Состояния системы")
        L.append("")
        for i in s["initial"]:
            L.append("Начальное: " + ", ".join(f"`{k}={v}`" for k, v in i.items()
                                               if k not in s["env"]))
        L.append("")
        L.append(f"Событий, меняющих состояние: **{len(s.get('transitions', []))}**")
        L.append("")
        for t in s.get("transitions", []):
            w = ", ".join(f"{k}={v}" for k, v in (t["when"] or {}).items()) or "из любого"
            st = ", ".join(f"{k}→{v}" for k, v in t["set"].items())
            L.append(f"- **{t['event']}** — когда {w}: {st}  · {t['evidence']}")
        L.append("")

    L.append("## Матрица")
    L.append("")
    L.append(f"{c['total']} комбинаций → {c['valid']} возможных → "
             f"**{c['collapsed']} строк** + {c['specials']} спецзначений")
    L.append("")
    cols = d["param_order"]
    L.append("| " + " | ".join(cols) + " | исход |")
    L.append("|" + "---|" * (len(cols) + 1))
    for r in s["rows"]:
        out = r["outcome"] or "**не описано**"
        L.append("| " + " | ".join(
            "∗" if r["values"][x] == "*" else str(r["values"][x]) for x in cols)
            + f" | {out} |")
    L.append("")

    if s["specials"]:
        L.append("Проверяются отдельно, по одному: "
                 + ", ".join(f"`{x['param']}={x['value']}`" for x in s["specials"]))
        L.append("")

    undef = [r for r in s["rows"] if r["status"] == "undefined"]
    if undef:
        L.append(f"## Непокрытые истории — {len(undef)}")
        L.append("")
        for r in undef:
            vv = ", ".join(f"`{k}={v}`" for k, v in r["values"].items()
                           if k not in s["env"] and v != "*")
            path = (" · путь: " + " → ".join(p["event"] for p in r["path"])) \
                if r.get("path") else (" · **недостижимо**" if r.get("reachable") is False else "")
            L.append(f"- {vv}{path}")
        L.append("")

    other = [f for f in s["findings"] if f["class"] != "UNDEFINED"]
    if other:
        L.append("## Находки")
        L.append("")
        seen = {}
        for f in other:
            seen.setdefault(f["class"], []).append(f)
        for k, v in seen.items():
            L.append(f"**{k}** ×{len(v)} — {v[0]['message']}")
            L.append("")

    q = [x for x in s["questions"] if not x["answered"]]
    if q:
        L.append("## Требуется уточнить")
        L.append("")
        for x in q:
            L.append(f"1. **{x['ask']}**")
            L.append(f"   моя догадка: {x['guess']} — {x['evidence']}")
            L.append(f"   без ответа {x['rows'] if 'rows' in x else x['cost_rows']} "
                     f"комбинаций остаются непроверенными")
            L.append("")

    print("\n".join(L))


if __name__ == "__main__":
    main()

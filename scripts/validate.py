#!/usr/bin/env python3
"""Инварианты модели. Падает с кодом 1 на первой ошибке класса error."""
import sys
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import store

def check(path):
    m = store.load(path)
    errs, warns = [], []
    P = m.get("params") or {}
    if not m.get("system"): errs.append("нет поля system")
    if not P: errs.append("нет параметров")

    for n, p in P.items():
        if not p.get("values"): errs.append(f"{n}: нет values")
        if not p.get("from"):   errs.append(f"{n}: нет from — источник значений не указан")
        if p.get("env") and (m.get("transitions") or []):
            for t in m["transitions"]:
                if n in (t.get("set") or {}):
                    errs.append(f"{n}: помечен env, но меняется переходом «{t['event']}»")

    def known(name, val, where):
        if name not in P: errs.append(f"{where}: неизвестный параметр «{name}»"); return
        for v in (val if isinstance(val, list) else [val]):
            if isinstance(v, str) and v.startswith("!"): continue
            if v not in P[name]["values"]:
                errs.append(f"{where}: значение «{v}» отсутствует в {name}.values")

    for i, c in enumerate(m.get("constraints") or []):
        w = f"constraints[{i}]"
        if not c.get("evidence"): errs.append(f"{w}: нет evidence")
        if c.get("status") not in ("proven", "assumed"):
            errs.append(f"{w}: status должен быть proven или assumed")
        if c.get("status") == "assumed" and not c.get("ask"):
            warns.append(f"{w}: assumed без ask — человек не поймёт, что подтверждает")
        for k, v in (c.get("forbid") or {}).items(): known(k, v, w + ".forbid")
        for k, v in (c.get("when") or {}).items():   known(k, v, w + ".when")
        for p in (c.get("irrelevant") or []):
            if p not in P: errs.append(f"{w}.irrelevant: неизвестный параметр «{p}»")

    for i, t in enumerate(m.get("transitions") or []):
        w = f"transitions[{i}] «{t.get('event','?')}»"
        if not t.get("event"): errs.append(f"{w}: нет event")
        if not t.get("set"):   errs.append(f"{w}: нет set")
        if not t.get("evidence"): errs.append(f"{w}: нет evidence")
        for k, v in (t.get("when") or {}).items(): known(k, v, w + ".when")
        for k, v in (t.get("set") or {}).items():  known(k, v, w + ".set")

    inits = m.get("initial")
    if inits:
        for i in (inits if isinstance(inits, list) else [inits]):
            for k, v in i.items(): known(k, v, "initial")
            miss = [n for n, p in P.items() if not p.get("env") and n not in i]
            if miss: errs.append(f"initial: не заданы параметры {miss}")
    elif m.get("transitions"):
        errs.append("есть transitions, но нет initial — достижимость не посчитать")

    for i, o in enumerate(m.get("outcomes") or []):
        w = f"outcomes[{i}]"
        if not o.get("behavior"): errs.append(f"{w}: нет behavior")
        for k, v in (o.get("match") or {}).items(): known(k, v, w + ".match")
    return errs, warns


if __name__ == "__main__":
    bad = 0
    for p in sys.argv[1:]:
        e, w = check(p)
        print(f"{p}: {'OK' if not e else str(len(e))+' ошибок'}"
              f"{', '+str(len(w))+' замечаний' if w else ''}")
        for x in e: print("  ERROR  " + x)
        for x in w: print("  warn   " + x)
        bad += len(e)
    sys.exit(1 if bad else 0)

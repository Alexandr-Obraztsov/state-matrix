#!/usr/bin/env python3
"""Инварианты модели. Падает с кодом 1 на первой ошибке класса error."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store


def check(path):
    m = store.load(path)
    if not isinstance(m, dict):
        return [f"{path}: это не модель (ожидался объект, получен {type(m).__name__})"], []
    errs, warns = [], []
    P = m.get("params") or {}
    if not m.get("system"): errs.append("нет поля system")
    if not P: errs.append("нет параметров")

    def known(name, val, where):
        """Имя параметра существует и значение объявлено у него."""
        if name not in P:
            errs.append(f"{where}: неизвестный параметр «{name}»")
            return
        for v in (val if isinstance(val, list) else [val]):
            if isinstance(v, str) and v.startswith("!"):
                continue
            if v not in [str(y) for y in (P[name].get("values") or [])]:
                errs.append(f"{where}: значение «{v}» отсутствует у {name}")

    for n, p in P.items():
        if not p.get("values"):
            errs.append(f"{n}: нет values — параметр объявлен, но значения не заданы")
        if not p.get("from"):   errs.append(f"{n}: нет from — источник значений не указан")
        av = p.get("all_values")
        if not av:
            errs.append(f"{n}: нет all_values — не перечислены все возможные значения")
        else:
            extra = [v for v in av if v not in p.get("values", [])]
            if extra and not p.get("grouping"):
                errs.append(f"{n}: {len(av)} значений свёрнуто в {len(p['values'])} "
                            f"классов без объяснения (нет grouping)")
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

    states = m.get("states") or []
    if not states:
        warns.append("нет ни одного состояния — матрица будет без исходов")
    seen_names = set()
    for i, o in enumerate(states):
        w = f"states[{i}] «{o.get('name','?')}»"
        if not o.get("name"):     errs.append(f"{w}: нет name")
        if not o.get("desc"):     errs.append(f"{w}: нет desc — что видит пользователь")
        if not o.get("evidence"): errs.append(f"{w}: нет evidence")
        if o.get("name") in seen_names:
            errs.append(f"{w}: имя состояния повторяется")
        seen_names.add(o.get("name"))
        for k, v in (o.get("when") or {}).items():
            known(k, v, w + ".when")
    # запасное состояние без условия обязано быть последним
    for i, o in enumerate(states[:-1]):
        if not (o.get("when") or {}):
            errs.append(f"states[{i}] «{o.get('name')}»: условия нет, но оно не последнее "
                        "— перекроет все состояния ниже")
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

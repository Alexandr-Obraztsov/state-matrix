#!/usr/bin/env python3
"""Инварианты модели. Падает с кодом 1 на первой ошибке класса error."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store

def semantics(model_path):
    """Дефолтная корзина плюс проектная; проектная имеет приоритет."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cat = {c["id"]: c for c in store.load(os.path.join(root, "catalog", "default.json"))}
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import sm
    d = os.path.dirname(model_path) or "."
    for cand in (os.path.join(d, "..", "catalog.json"), os.path.join(d, "catalog.json")):
        for c in (store.load(cand) or []):
            cat[c["id"]] = sm.merge_entry(cat[c["id"]], c) if c["id"] in cat else c
    return cat


def check(path):
    m = store.load(path)
    if not isinstance(m, dict):
        return [f"{path}: это не модель (ожидался объект, получен {type(m).__name__})"], []
    errs, warns = [], []
    P = m.get("params") or {}
    CAT = semantics(path)
    if not m.get("system"): errs.append("нет поля system")
    if not P: errs.append("нет параметров")

    for n, p in P.items():
        if not p.get("values"): errs.append(f"{n}: нет values")
        if not p.get("from"):   errs.append(f"{n}: нет from — источник значений не указан")
        av = p.get("all_values")
        if not av:
            errs.append(f"{n}: нет all_values — не перечислены все возможные значения")
        else:
            extra = [v for v in av if v not in p.get("values", [])]
            if extra and not p.get("grouping"):
                errs.append(f"{n}: {len(av)} значений свёрнуто в {len(p['values'])} "
                            f"классов без объяснения (нет grouping)")
        cid = p.get("catalog")
        if cid:
            if cid not in CAT:
                errs.append(f"{n}: семантика «{cid}» отсутствует в корзине")
            else:
                ans = p.get("answers") or {}
                for q in CAT[cid]["questions"]:
                    if q["id"] not in ans:
                        errs.append(f"{n}: нет ответа на вопрос «{q['id']}» семантики {cid}"
                                    " — параметр добавлен в обход sm.py")
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

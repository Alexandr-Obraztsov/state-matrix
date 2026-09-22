#!/usr/bin/env python3
"""Единственный способ изменить модель состояний.

  init → param add (все) → ВОРОТА → param values (каждый) → ВОРОТА
       → state add (все варианты UI) → ВОРОТА → rule add → build → ВОРОТА
"""
import os, sys, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store, validate, engine

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI_HINT = ("покрой ВСЕ варианты интерфейса: элемент показан и скрыт, загрузка, "
           "пусто, ошибка, заблокировано, свёрнуто, данные неполные")


def die(msg, hint=""):
    print(f"ОТКАЗ: {msg}", file=sys.stderr)
    if hint:
        print(f"  {hint}", file=sys.stderr)
    sys.exit(2)


def load(path):
    m = store.load(path)
    if not m:
        die(f"нет модели {path}", "завести: sm.py init <модель> --system … --source …")
    return m


def pairs(spec, P):
    """«параметр=значение» или «параметр=знач1,знач2», с проверкой по модели."""
    d = {}
    for x in spec or []:
        if "=" not in x:
            die(f"«{x}» не похоже на параметр=значение")
        k, v = x.split("=", 1)
        if k not in P:
            die(f"неизвестный параметр «{k}»", f"объявленные: {', '.join(P) or '—'}")
        known = [str(y) for y in (P[k].get("values") or [])]
        vals = v.split(",")
        for z in vals:
            if known and z not in known:
                die(f"значение «{z}» отсутствует у {k}", f"есть: {', '.join(known)}")
        d[k] = vals if len(vals) > 1 else vals[0]
    return d


def ref_ok(text, model_path, root):
    return validate.check_ref(text, store.load(model_path).get("source", ""), root)


# ---------- модель ----------

def cmd_init(a):
    if os.path.exists(a.model) and not a.force:
        die(f"модель {a.model} уже есть", "перезаписать: --force")
    store.save(a.model, {"system": a.system, "source": a.source,
                         "params": {}, "excluded": {}, "constraints": [], "states": []})
    print(f"модель заведена: {a.model}")
    print("дальше: прочитай спеку и всё, на что она ссылается, затем объяви ВСЕ "
          "параметры — значения зададутся после одобрения перечня")


# ---------- этап 1: перечень параметров ----------

def cmd_param_add(a):
    if not a.desc:
        die("не указан --desc", "что это за вход — одной фразой")
    if not a.frm:
        die("не указан --from", "ссылка на место в спеке: docs/spec.md:§3")
    m = load(a.model)
    ok, why = ref_ok(a.frm, a.model, a.root)
    if not ok:
        die(f"--from не подтверждается: {why}",
            "ссылка должна указывать на существующий раздел спеки")
    m.setdefault("params", {})
    if a.name in m["params"] and not a.force:
        die(f"параметр «{a.name}» уже объявлен", "перезаписать: --force")
    m["params"][a.name] = {"type": a.type, "desc": a.desc, "from": a.frm}
    store.save(a.model, m)
    print(f"«{a.name}» объявлен — параметров всего {len(m['params'])}")


def cmd_param_rm(a):
    m = load(a.model)
    if a.name not in (m.get("params") or {}):
        die(f"параметра «{a.name}» нет")
    del m["params"][a.name]
    for c in list(m.get("constraints") or []):
        if a.name in (set(c.get("forbid") or {}) | set(c.get("when") or {})
                      | set(c.get("irrelevant") or [])):
            m["constraints"].remove(c)
            print(f"  заодно убрано правило {c.get('id')}")
    for st in list(m.get("states") or []):
        if a.name in (st.get("when") or {}):
            m["states"].remove(st)
            print(f"  заодно убрано состояние «{st['name']}»")
    store.save(a.model, m)
    print(f"«{a.name}» убран")


def cmd_exclude(a):
    m = load(a.model)
    m.setdefault("excluded", {})[a.name] = a.reason
    store.save(a.model, m)
    print(f"«{a.name}» исключён: {a.reason}")


def cmd_params(a):
    m = load(a.model)
    P = m.get("params") or {}
    if not P:
        die("параметров пока нет", f"объявить: sm.py param add {a.model} --name …")
    w = max(len(n) for n in P)
    print(f"{m.get('system','—')} — параметров {len(P)}\n")
    for n, p in P.items():
        left = "" if p.get("values") else "   ← значения не заданы"
        print(f"  {n:{w}}  {p.get('type','—'):9}{left}")
        print(f"  {'':{w}}  {p.get('desc','')}")
        print(f"  {'':{w}}  {p.get('from','—')}")
    if m.get("excluded"):
        print("\nисключено: " + "; ".join(f"{k} — {v}" for k, v in m["excluded"].items()))
    left = [n for n, p in P.items() if not p.get("values")]
    print(f"\nзначения заданы у {len(P) - len(left)} из {len(P)}"
          + (f"; ждут: {', '.join(left)}" if left else ""))


# ---------- этап 2: значения ----------

def cmd_param_values(a):
    m = load(a.model)
    p = (m.get("params") or {}).get(a.name)
    if p is None:
        die(f"параметр «{a.name}» не объявлен",
            f"сначала: sm.py param add {a.model} --name {a.name} …")
    if not a.all_values:
        die("не указаны --all-values",
            "перечисли ВСЕ значения из спеки, включая корнер-кейсы")
    values = a.values or list(a.all_values)
    extra = [v for v in a.all_values if v not in values]
    if extra and not a.grouping:
        die(f"{len(a.all_values)} значений свёрнуто в {len(values)} классов без объяснения",
            f"нужен --grouping: почему они дают один исход. вне классов: {', '.join(extra[:8])}")
    p["all_values"] = list(a.all_values)
    p["values"] = values
    if a.grouping:
        p["grouping"] = a.grouping
    if a.special:
        p["special"] = list(a.special)
    store.save(a.model, m)
    if extra:
        print(f"«{a.name}»: {len(a.all_values)} значений → {len(values)} классов")
        print(f"  основание: {a.grouping}")
    else:
        print(f"«{a.name}»: {len(values)} значений, объединений нет")
    if a.special:
        print(f"  вне матрицы, по одному: {', '.join(a.special)}")
    left = [n for n, x in m["params"].items() if not x.get("values")]
    print(f"  без значений осталось: {', '.join(left) if left else '—'}")


# ---------- этап 3: состояния ----------

def cmd_state_add(a):
    m = load(a.model)
    if not a.desc:
        die("нет --desc", "что пользователь видит в этом состоянии")
    if not a.evidence:
        die("нет --evidence", "ссылка на место в спеке: docs/spec.md:§3")
    ok, why = ref_ok(a.evidence, a.model, a.root)
    if not ok:
        die(f"--evidence не подтверждается: {why}",
            "состояния без ссылки не бывает; если в спеке его нет — спроси пользователя")
    when = pairs(a.when, m.get("params") or {})
    m.setdefault("states", []).append(
        {"name": a.name, "when": when, "desc": a.desc, "evidence": a.evidence})
    store.save(a.model, m)
    print(f"«{a.name}» добавлено — состояний всего {len(m['states'])}")
    print(f"  когда: {when or 'всегда (запасное — только последним)'}")


def cmd_state_rm(a):
    m = load(a.model)
    before = len(m.get("states") or [])
    m["states"] = [s for s in (m.get("states") or []) if s.get("name") != a.name]
    if len(m["states"]) == before:
        die(f"состояния «{a.name}» нет")
    store.save(a.model, m)
    print(f"«{a.name}» убрано")


def cmd_states(a):
    m = load(a.model)
    S = m.get("states") or []
    if not S:
        die("состояний пока нет", UI_HINT)
    print(f"{m.get('system','—')} — состояний {len(S)}"
          "   (порядок значим: побеждает первое подходящее)\n")
    for i, x in enumerate(S, 1):
        w = " · ".join(f"{k} = {', '.join(v) if isinstance(v, list) else v}"
                       for k, v in (x.get("when") or {}).items()) or "всегда"
        print(f"  {i}. {x['name']}")
        print(f"     когда: {w}")
        print(f"     видно: {x.get('desc','')}")
        print(f"     {x.get('evidence','—')}")
    print(f"\n{UI_HINT}")


# ---------- этап 4: правила и матрица ----------

def cmd_rule_add(a):
    m = load(a.model)
    P = m.get("params") or {}
    if not P:
        die("в модели нет параметров")
    if not a.evidence:
        die("нет --evidence", "правило без основания не принимается")
    ok, why = ref_ok(a.evidence, a.model, a.root)
    if not ok:
        die(f"--evidence не подтверждается: {why}",
            "правило берётся только из спеки. Нет в спеке — спроси пользователя "
            "и попроси показать место, откуда это следует")
    r = {"id": a.id, "evidence": a.evidence}
    if a.desc:
        r["desc"] = a.desc
    if a.forbid:
        r["forbid"] = pairs(a.forbid, P)
    elif a.irrelevant:
        for x in a.irrelevant:
            if x not in P:
                die(f"неизвестный параметр «{x}»")
        r["when"] = pairs(a.when, P)
        r["irrelevant"] = list(a.irrelevant)
    else:
        die("нужно либо --forbid, либо --irrelevant")
    m.setdefault("constraints", []).append(r)
    store.save(a.model, m)
    print(f"правило {a.id} добавлено — правил всего {len(m['constraints'])}")


def cmd_rule_rm(a):
    m = load(a.model)
    before = len(m.get("constraints") or [])
    m["constraints"] = [c for c in (m.get("constraints") or []) if c.get("id") != a.id]
    if len(m["constraints"]) == before:
        die(f"правила «{a.id}» нет")
    store.save(a.model, m)
    print(f"правило «{a.id}» убрано")


def table(cols, rows):
    w = {c: max([len(c)] + [len(str(r["values"][c])) for r in rows]) for c in cols}
    ws = max([len("состояние")] + [len(r["state"] or "не определено") for r in rows])
    out = ["  " + "  ".join(c.ljust(w[c]) for c in cols) + "  | " + "состояние".ljust(ws)
           + " | что видно",
           "  " + "  ".join("-" * w[c] for c in cols) + "--+-" + "-" * ws + "-+-" + "-" * 30]
    for r in rows:
        out.append("  " + "  ".join(str(r["values"][c]).ljust(w[c]) for c in cols)
                   + "  | " + (r["state"] or "НЕ ОПРЕДЕЛЕНО").ljust(ws)
                   + " | " + (r.get("desc") or ""))
    return "\n".join(out)


def show_result(res):
    c = res["counts"]
    print(f"\n{res['system']}   {res['source']}")
    print(f"\n{c['total']} комбинаций → {c['valid']} возможных → {c['collapsed']} строк"
          f" + {c['specials']} спецзначений")
    print("\nСОСТОЯНИЯ")
    for st in res["states"]:
        print(f"  {st['rows']:3}  {st['name']}")
    if c["no_state"]:
        print(f"  {c['no_state']:3}  ← НЕ ОПРЕДЕЛЕНО: разбери, sm.py rows … --no-state")
    print("\nМАТРИЦА")
    print(table(res["param_order"], res["rows"]))
    if res["specials"]:
        print("\nВНЕ МАТРИЦЫ, проверяются по одному:")
        for x in res["specials"]:
            print(f"  {x['param']} = {x['value']}")
    if res["findings"]:
        print("\nНАХОДКИ")
        for f in res["findings"]:
            print(f"  [{f['severity']}] {f['class']}: {f['message']}")


def cmd_build(a):
    m = load(a.model)
    no_vals = [n for n, p in (m.get("params") or {}).items() if not p.get("values")]
    if no_vals:
        die(f"у параметров нет значений: {', '.join(no_vals)}",
            "сначала param values по каждому")
    if not (m.get("states") or []):
        die("нет ни одного состояния", "матрица без состояний — таблица без исходов. " + UI_HINT)
    errs, warns = validate.check(a.model, a.root)
    for x in warns:
        print(f"замечание: {x}")
    if errs:
        for x in errs:
            print(f"ОШИБКА: {x}", file=sys.stderr)
        die("модель не прошла проверку", "матрица не собрана")
    res = engine.build(m)
    out = os.path.normpath(os.path.join(os.path.dirname(a.model) or ".", "..", "runs",
                                        os.path.basename(a.model).replace(".states.json", "")
                                        + ".json"))
    store.save(out, res)
    show_result(res)


def cmd_rows(a):
    res = store.load(a.result)
    if not res:
        die(f"нет {a.result}", "сначала: sm.py build <модель>")
    rows = [r for r in res["rows"] if not r["state"]] if a.no_state else res["rows"]
    print(f"{len(rows)} строк из {len(res['rows'])}\n")
    for r in rows[:a.limit]:
        vv = ", ".join(f"{k}={v}" for k, v in r["values"].items() if v != "*")
        print(f"  {r['id']}  {vv}")
        if r["covers"] > 1:
            print(f"      покрывает {r['covers']} комбинаций")


def cmd_show(a):
    m = load(a.model)
    print(f"{m.get('system','—')}   {m.get('source','—')}")
    P = m.get("params") or {}
    print(f"\nПАРАМЕТРЫ ({len(P)})")
    for n, p in P.items():
        print(f"\n  {n} — {p.get('type','—')}")
        print(f"      {p.get('desc','')}")
        av, vv = p.get("all_values") or [], p.get("values") or []
        if not vv:
            print("      значения не заданы")
        elif len(av) != len(vv):
            print(f"      все значения ({len(av)}): {', '.join(map(str, av))}")
            print(f"      классы ({len(vv)}): {', '.join(map(str, vv))}")
            print(f"      объединены: {p.get('grouping','— без основания —')}")
        else:
            print(f"      значения: {', '.join(map(str, vv))}")
        if p.get("special"):
            print(f"      вне матрицы: {', '.join(map(str, p['special']))}")
        print(f"      источник: {p.get('from','—')}")
    if m.get("excluded"):
        print(f"\nИСКЛЮЧЕНО ({len(m['excluded'])})")
        for k, v in m["excluded"].items():
            print(f"  {k} — {v}")
    C = m.get("constraints") or []
    print(f"\nПРАВИЛА ({len(C)})")
    for c in C:
        kind = "запрет" if "forbid" in c else "схлопывание"
        print(f"  {c.get('id')}  {kind}: {c.get('desc') or c.get('evidence')}")
        print(f"      {c.get('evidence')}")
    S = m.get("states") or []
    print(f"\nСОСТОЯНИЯ ({len(S)})")
    for x in S:
        w = ", ".join(f"{k}={v}" for k, v in (x.get("when") or {}).items()) or "всегда"
        print(f"  {x['name']}: {w}")


def main():
    ap = argparse.ArgumentParser(prog="sm.py")
    ap.add_argument("--root", default=".", help="корень репозитория для проверки ссылок")
    sub = ap.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("init"); i.add_argument("model")
    i.add_argument("--system", required=True); i.add_argument("--source", required=True)
    i.add_argument("--force", action="store_true"); i.set_defaults(fn=cmd_init)

    p = sub.add_parser("param").add_subparsers(dest="x", required=True)
    pa = p.add_parser("add"); pa.add_argument("model")
    pa.add_argument("--name", required=True); pa.add_argument("--type", required=True)
    pa.add_argument("--desc"); pa.add_argument("--from", dest="frm")
    pa.add_argument("--force", action="store_true"); pa.set_defaults(fn=cmd_param_add)
    pv = p.add_parser("values"); pv.add_argument("model")
    pv.add_argument("--name", required=True)
    pv.add_argument("--all-values", nargs="+", dest="all_values")
    pv.add_argument("--values", nargs="*"); pv.add_argument("--grouping")
    pv.add_argument("--special", nargs="*"); pv.set_defaults(fn=cmd_param_values)
    pr = p.add_parser("rm"); pr.add_argument("model"); pr.add_argument("name")
    pr.set_defaults(fn=cmd_param_rm)

    ps = sub.add_parser("params"); ps.add_argument("model"); ps.set_defaults(fn=cmd_params)
    ex = sub.add_parser("exclude"); ex.add_argument("model"); ex.add_argument("name")
    ex.add_argument("reason"); ex.set_defaults(fn=cmd_exclude)

    st = sub.add_parser("state").add_subparsers(dest="x", required=True)
    sa = st.add_parser("add"); sa.add_argument("model")
    sa.add_argument("--name", required=True); sa.add_argument("--when", nargs="*")
    sa.add_argument("--desc"); sa.add_argument("--evidence"); sa.set_defaults(fn=cmd_state_add)
    sr = st.add_parser("rm"); sr.add_argument("model"); sr.add_argument("name")
    sr.set_defaults(fn=cmd_state_rm)
    ss = sub.add_parser("states"); ss.add_argument("model"); ss.set_defaults(fn=cmd_states)

    r = sub.add_parser("rule").add_subparsers(dest="x", required=True)
    ra = r.add_parser("add"); ra.add_argument("model"); ra.add_argument("--id", required=True)
    ra.add_argument("--forbid", nargs="*"); ra.add_argument("--when", nargs="*")
    ra.add_argument("--irrelevant", nargs="*"); ra.add_argument("--evidence")
    ra.add_argument("--desc"); ra.set_defaults(fn=cmd_rule_add)
    rr = r.add_parser("rm"); rr.add_argument("model"); rr.add_argument("id")
    rr.set_defaults(fn=cmd_rule_rm)

    sh = sub.add_parser("show"); sh.add_argument("model"); sh.set_defaults(fn=cmd_show)
    rw = sub.add_parser("rows"); rw.add_argument("result")
    rw.add_argument("--no-state", action="store_true", dest="no_state")
    rw.add_argument("--limit", type=int, default=50); rw.set_defaults(fn=cmd_rows)
    b = sub.add_parser("build"); b.add_argument("model"); b.set_defaults(fn=cmd_build)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

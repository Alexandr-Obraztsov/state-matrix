#!/usr/bin/env python3
"""Единственный способ изменить модель состояний.

Порядок жёсткий, каждый шаг отказывает при нарушении:

  init  →  param add (все)  →  ВОРОТА  →  param values (каждый)  →  ВОРОТА
        →  state add (все варианты UI)  →  ВОРОТА
        →  rule add  →  build  →  ВОРОТА
"""
import os, sys, json, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def die(msg, hint=""):
    print(f"ОТКАЗ: {msg}", file=sys.stderr)
    if hint:
        print(f"  {hint}", file=sys.stderr)
    sys.exit(2)


def load_model(p):
    return store.load(p)


def save_model(p, m):
    store.save(p, m)


def need(m, path):
    if not m:
        die(f"нет модели {path}", "завести: sm.py init <модель> --system … --source …")
    return m


def pairs(spec, P, allow_bang=False):
    """«параметр=значение» или «параметр=знач1,знач2» с проверкой по модели."""
    d = {}
    for x in spec or []:
        if "=" not in x:
            die(f"«{x}» не похоже на параметр=значение")
        k, v = x.split("=", 1)
        if k not in P:
            die(f"неизвестный параметр «{k}»",
                f"объявленные: {', '.join(P) or '—'}")
        known = [str(y) for y in (P[k].get("values") or [])]
        vals = v.split(",")
        for z in vals:
            if allow_bang and z.startswith("!"):
                continue
            if known and z not in known:
                die(f"значение «{z}» отсутствует у параметра {k}",
                    f"есть: {', '.join(known)}")
        d[k] = vals if len(vals) > 1 else vals[0]
    return d


def has_ref(text):
    """Ссылка вида file.md:§3 или file.ts:27 — иначе это не доказательство."""
    if not text or ":" not in text:
        return False
    tail = text.split(":")[-1][:8]
    return "§" in text or any(ch.isdigit() for ch in tail)


# ---------- модель ----------

def cmd_init(a):
    if os.path.exists(a.model) and not a.force:
        die(f"модель {a.model} уже есть", "перезаписать: --force")
    save_model(a.model, {"system": a.system, "source": a.source, "params": {},
                         "excluded": {}, "constraints": [], "transitions": [],
                         "states": []})
    print(f"модель заведена: {a.model}")
    print("дальше: изучи спеку и все ссылки из неё, потом объяви ВСЕ параметры"
          " через param add — значения задашь после одобрения перечня")


# ---------- этап 1: перечень параметров ----------

def cmd_param_add(a):
    """Объявить параметр. Значения задаются отдельно, после ворот."""
    if not a.frm:
        die("не указан --from", "нужна ссылка на место в спеке: docs/spec.md:§3")
    if not a.desc:
        die("не указан --desc", "что это за вход и откуда берётся — одной фразой")
    m = need(load_model(a.model), a.model)
    m.setdefault("params", {})
    if a.name in m["params"] and not a.force:
        die(f"параметр «{a.name}» уже объявлен", "перезаписать: --force")
    p = {"type": a.type, "desc": a.desc, "from": a.frm}
    if a.env:
        p["env"] = True
    m["params"][a.name] = p
    save_model(a.model, m)
    print(f"«{a.name}» объявлен — параметров всего {len(m['params'])}")


def cmd_param_rm(a):
    m = need(load_model(a.model), a.model)
    if a.name not in (m.get("params") or {}):
        die(f"параметра «{a.name}» нет")
    del m["params"][a.name]
    for c in list(m.get("constraints") or []):
        used = set(c.get("forbid") or {}) | set(c.get("when") or {}) | set(c.get("irrelevant") or [])
        if a.name in used:
            m["constraints"].remove(c)
            print(f"  заодно убрано правило {c.get('id')} — ссылалось на параметр")
    for st in list(m.get("states") or []):
        if a.name in (st.get("when") or {}):
            m["states"].remove(st)
            print(f"  заодно убрано состояние «{st['name']}» — ссылалось на параметр")
    save_model(a.model, m)
    print(f"«{a.name}» убран")


def cmd_exclude(a):
    m = need(load_model(a.model), a.model)
    m.setdefault("excluded", {})[a.name] = a.reason
    save_model(a.model, m)
    print(f"«{a.name}» исключён: {a.reason}")


def cmd_params(a):
    """Перечень параметров — для ворот «все ли это параметры?»."""
    m = need(load_model(a.model), a.model)
    P = m.get("params") or {}
    if not P:
        die("параметров пока нет", f"объявить: sm.py param add {a.model} --name …")
    w = max(len(n) for n in P)
    print(f"{m.get('system','—')} — параметров {len(P)}\n")
    for n, p in P.items():
        env = "  [окружение]" if p.get("env") else ""
        left = "" if p.get("values") else "   ← значения не заданы"
        print(f"  {n:{w}}  {p.get('type','—'):9}{env}{left}")
        print(f"  {'':{w}}  {p.get('desc','')}")
        print(f"  {'':{w}}  {p.get('from','—')}")
    if m.get("excluded"):
        print(f"\nисключено: " + "; ".join(f"{k} — {v}" for k, v in m["excluded"].items()))
    no_vals = [n for n, p in P.items() if not p.get("values")]
    print(f"\nзначения заданы у {len(P)-len(no_vals)} из {len(P)}"
          + (f"; ждут: {', '.join(no_vals)}" if no_vals else ""))


# ---------- этап 2: значения ----------

def cmd_param_values(a):
    """Все значения параметра, затем объединение в классы с основанием."""
    m = need(load_model(a.model), a.model)
    p = (m.get("params") or {}).get(a.name)
    if p is None:
        die(f"параметр «{a.name}» не объявлен",
            f"сначала: sm.py param add {a.model} --name {a.name} …")
    if not a.all_values:
        die("не указаны --all-values",
            "перечисли ВСЕ значения из спеки, включая корнер-кейсы, "
            "и только потом объединяй в классы")
    values = a.values or list(a.all_values)
    extra = [v for v in a.all_values if v not in values]
    if extra and not a.grouping:
        die(f"{len(a.all_values)} значений свёрнуто в {len(values)} классов без объяснения",
            "нужен --grouping: почему эти значения дают один исход. "
            f"вне классов: {', '.join(extra[:8])}")
    p.update({"all_values": list(a.all_values), "values": values})
    if a.grouping:
        p["grouping"] = a.grouping
    if a.special:
        p["special"] = list(a.special)
    m["params"][a.name] = {k: p[k] for k in ("type", "desc", "all_values", "values",
                                             "grouping", "special", "from", "env")
                           if k in p}
    save_model(a.model, m)
    if extra:
        print(f"«{a.name}»: {len(a.all_values)} значений → {len(values)} классов")
        print(f"  основание: {a.grouping}")
    else:
        print(f"«{a.name}»: {len(values)} значений, объединений нет")
    if a.special:
        print(f"  вне матрицы, проверяются по одному: {', '.join(a.special)}")
    left = [n for n, x in m["params"].items() if not x.get("values")]
    print(f"  без значений осталось: {', '.join(left) if left else '—'}")


# ---------- этап 3: состояния ----------

UI_HINT = ("покрой ВСЕ варианты интерфейса: элемент показан и скрыт, загрузка,"
           " пусто, ошибка, заблокировано, свёрнуто, частичные данные")


def cmd_state_add(a):
    m = need(load_model(a.model), a.model)
    P = m.get("params") or {}
    if not a.evidence:
        die("нет --evidence", "состояние должно ссылаться на место в спеке")
    if not has_ref(a.evidence):
        die("в --evidence нет ссылки вида docs/spec.md:§3",
            "состояние без ссылки — выдумка; если в спеке его нет, спроси пользователя")
    if not a.desc:
        die("нет --desc", "что пользователь видит в этом состоянии — одной фразой")
    when = pairs(a.when, P)
    m.setdefault("states", []).append(
        {"name": a.name, "when": when, "desc": a.desc, "evidence": a.evidence})
    save_model(a.model, m)
    print(f"состояние «{a.name}» добавлено — всего {len(m['states'])}")
    print(f"  условие: {when or 'всегда (запасное — ставь последним)'}")


def cmd_state_rm(a):
    m = need(load_model(a.model), a.model)
    before = len(m.get("states") or [])
    m["states"] = [s for s in (m.get("states") or []) if s.get("name") != a.name]
    if len(m["states"]) == before:
        die(f"состояния «{a.name}» нет")
    save_model(a.model, m)
    print(f"состояние «{a.name}» убрано")


def cmd_states(a):
    """Состояния — для ворот. Порядок значим: побеждает первое подходящее."""
    m = need(load_model(a.model), a.model)
    S_ = m.get("states") or []
    if not S_:
        die("состояний пока нет", UI_HINT)
    print(f"{m.get('system','—')} — состояний {len(S_)}"
          "   (порядок значим: побеждает первое подходящее)\n")
    for i, x in enumerate(S_, 1):
        w = " · ".join(f"{k} = {', '.join(v) if isinstance(v, list) else v}"
                       for k, v in (x.get("when") or {}).items()) or "всегда"
        print(f"  {i}. {x['name']}")
        print(f"     когда: {w}")
        print(f"     видно: {x.get('desc','')}")
        print(f"     {x.get('evidence','—')}")
    print(f"\n{UI_HINT}")


# ---------- этап 4: правила, переходы, матрица ----------

def cmd_rule_add(a):
    m = need(load_model(a.model), a.model)
    P = m.get("params") or {}
    if not P:
        die("в модели нет параметров")
    if not a.evidence:
        die("нет --evidence", "правило без основания не принимается")
    status = "proven" if has_ref(a.evidence) and not a.assumed else "assumed"
    if status == "assumed" and not a.ask:
        die("правило без ссылки вида spec.md:§3 становится assumed и требует --ask",
            "сформулируй вопрос пользователю одной фразой")
    r = {"id": a.id, "evidence": a.evidence, "status": status}
    if a.desc:
        r["desc"] = a.desc
    if a.ask:
        r["ask"] = a.ask
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
    save_model(a.model, m)
    print(f"правило {a.id} добавлено, статус {status}"
          + ("  — в матрицу не пойдёт, пока не подтвердят" if status == "assumed" else ""))


def cmd_rule_rm(a):
    m = need(load_model(a.model), a.model)
    before = len(m.get("constraints") or [])
    m["constraints"] = [c for c in (m.get("constraints") or []) if c.get("id") != a.id]
    if len(m["constraints"]) == before:
        die(f"правила «{a.id}» нет")
    save_model(a.model, m)
    print(f"правило «{a.id}» убрано")


def cmd_transition_add(a):
    m = need(load_model(a.model), a.model)
    P = m.get("params") or {}
    if not a.evidence:
        die("нет --evidence", "переход должен ссылаться на место в спеке")
    if not a.set:
        die("нет --set", "переход обязан что-то менять")
    t = {"event": a.event, "when": pairs(a.when, P),
         "set": pairs(a.set, P, allow_bang=True), "evidence": a.evidence}
    m.setdefault("transitions", []).append(t)
    save_model(a.model, m)
    print(f"переход «{a.event}» добавлен — всего {len(m['transitions'])}")


def cmd_answer(a):
    p = os.path.join(os.path.dirname(a.model) or ".", "answers.json")
    cur = store.load(p) or {}
    cur.setdefault(a.section, {})[a.id] = a.value
    store.save(p, cur)
    print(f"{a.section}.{a.id} = {a.value}")


# ---------- вывод матрицы ----------

def table(cols, rows, extra):
    w = {c: max(len(c), *(len(str(r["values"][c])) for r in rows)) for c in cols} if rows else {}
    w2 = max([len(r.get(extra) or "") for r in rows] + [len(extra)]) if rows else 0
    out = ["  " + "  ".join(c.ljust(w[c]) for c in cols) + "  | " + extra,
           "  " + "  ".join("-" * w[c] for c in cols) + "--+-" + "-" * w2]
    for r in rows:
        out.append("  " + "  ".join(str(r["values"][c]).ljust(w[c]) for c in cols)
                   + "  | " + (r.get(extra) or "— не определено —"))
    return "\n".join(out)


def cmd_build(a):
    """verify → validate → engine. Печатает сводку и матрицу, без файлов-отчётов."""
    import subprocess
    sc = lambda n: os.path.join(ROOT, "scripts", n)
    m = need(load_model(a.model), a.model)
    no_vals = [n for n, p in (m.get("params") or {}).items() if not p.get("values")]
    if no_vals:
        die(f"у параметров нет значений: {', '.join(no_vals)}",
            "матрицу считать не из чего — сначала param values по каждому")
    if not (m.get("states") or []):
        die("нет ни одного состояния",
            "матрица без состояний — таблица без исходов. " + UI_HINT)

    name = os.path.basename(a.model).replace(".states.json", "")
    out = os.path.normpath(os.path.join(os.path.dirname(a.model) or ".", "..",
                                        "runs", name + ".json"))
    for cmd in ([sys.executable, sc("verify.py"), a.model, "--root", a.root],
                [sys.executable, sc("validate.py"), a.model],
                [sys.executable, sc("engine.py"), a.model, "-a",
                 os.path.join(os.path.dirname(a.model) or ".", "..", "answers.json"),
                 "-o", out]):
        r = subprocess.run(cmd, text=True, capture_output=True)
        text = (r.stdout or "") + (r.stderr or "")
        if text.strip():
            print(text.rstrip())
        if r.returncode:
            die(f"шаг не прошёл: {os.path.basename(cmd[1])}", "матрица не собрана")
    print_result(out, a.env)


def print_result(path, env=0):
    res = store.load(path)
    sl = res["slices"][env]
    c = sl["counts"]
    envname = ", ".join(f"{k}={v}" for k, v in sl["env"].items())
    print(f"\n{res['system']}" + (f"   окружение: {envname}" if envname else ""))
    if len(res["slices"]) > 1:
        print(f"окружений {len(res['slices'])}, показано первое"
              f" — остальные: sm.py result {path} --env N")
    print(f"\n{c['total']} комбинаций → {c['valid']} возможных → {c['collapsed']} строк"
          f" + {c['specials']} спецзначений")

    print(f"\nСОСТОЯНИЯ")
    for st in sl.get("states", []):
        print(f"  {st['rows']:3}  {st['name']}")
    if sl.get("no_state"):
        print(f"  {sl['no_state']:3}  ← БЕЗ СОСТОЯНИЯ: разбери их, sm.py rows … --no-state")

    print(f"\nМАТРИЦА")
    print(table(res["param_order"], sl["rows"], "state"))
    if sl["specials"]:
        print("\nВНЕ МАТРИЦЫ, проверяются по одному:")
        for x in sl["specials"]:
            print(f"  {x['param']} = {x['value']}")

    q = [x for x in sl["questions"] if not x["answered"]]
    if q:
        print(f"\nТРЕБУЕТ ОТВЕТА ({len(q)})")
        for x in q:
            print(f"  {x['ask']}")
            print(f"    догадка: {x['guess']} — {x['evidence']}")
            print(f"    без ответа {x['cost_rows']} комбинаций не проверены")
    other = [f for f in sl["findings"] if f["class"] != "UNDEFINED"]
    if other:
        print(f"\nНАХОДКИ")
        for f in other:
            print(f"  [{f['severity']}] {f['class']}: {f['message']}")


def cmd_result(a):
    print_result(a.result, a.env)


def cmd_rows(a):
    res = store.load(a.result)
    if not res:
        die(f"нет {a.result}", "сначала: sm.py build <модель>")
    sl = res["slices"][a.env]
    rows = sl["rows"]
    if a.no_state:
        rows = [r for r in rows if not r.get("state")]
    if a.status:
        rows = [r for r in rows if r["status"] == a.status]
    print(f"{len(rows)} строк из {len(sl['rows'])}\n")
    for r in rows[:a.limit]:
        vv = ", ".join(f"{k}={v}" for k, v in r["values"].items() if v != "*")
        print(f"  {r['id']}  {vv}")
        if r.get("path"):
            print(f"      путь: " + " → ".join(p["event"] for p in r["path"]))
        elif r.get("reachable") is False:
            print("      недостижимо ни одной цепочкой событий")


def cmd_show(a):
    m = need(load_model(a.model), a.model)
    print(f"{m.get('system','—')}   {m.get('source','—')}")
    P = m.get("params") or {}
    print(f"\nПАРАМЕТРЫ ({len(P)})")
    for n, p in P.items():
        env = "  [окружение]" if p.get("env") else ""
        print(f"\n  {n}{env} — {p.get('type','—')}")
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
        print(f"  [{c.get('status','?'):7}] {c.get('id')}  {kind}: "
              f"{c.get('desc') or c.get('evidence')}")
    S_ = m.get("states") or []
    print(f"\nСОСТОЯНИЯ ({len(S_)})")
    for x in S_:
        w = ", ".join(f"{k}={v}" for k, v in (x.get("when") or {}).items()) or "всегда"
        print(f"  {x['name']}: {w}")
    T = m.get("transitions") or []
    if T:
        print(f"\nПЕРЕХОДЫ ({len(T)})")
        for t in T:
            w = ", ".join(f"{k}={v}" for k, v in (t.get("when") or {}).items()) or "из любого"
            print(f"  {t['event']}: когда {w} → "
                  + ", ".join(f"{k}→{v}" for k, v in t["set"].items()))


def main():
    ap = argparse.ArgumentParser(prog="sm.py")
    sub = ap.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("init"); i.add_argument("model")
    i.add_argument("--system", required=True); i.add_argument("--source", required=True)
    i.add_argument("--force", action="store_true"); i.set_defaults(fn=cmd_init)

    p = sub.add_parser("param").add_subparsers(dest="x", required=True)
    pa = p.add_parser("add"); pa.add_argument("model")
    pa.add_argument("--name", required=True); pa.add_argument("--type", required=True)
    pa.add_argument("--desc"); pa.add_argument("--from", dest="frm")
    pa.add_argument("--env", action="store_true"); pa.add_argument("--force", action="store_true")
    pa.set_defaults(fn=cmd_param_add)
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
    ra.add_argument("--desc"); ra.add_argument("--ask")
    ra.add_argument("--assumed", action="store_true"); ra.set_defaults(fn=cmd_rule_add)
    rr = r.add_parser("rm"); rr.add_argument("model"); rr.add_argument("id")
    rr.set_defaults(fn=cmd_rule_rm)

    tr = sub.add_parser("transition").add_subparsers(dest="x", required=True)
    ta = tr.add_parser("add"); ta.add_argument("model"); ta.add_argument("--event", required=True)
    ta.add_argument("--when", nargs="*"); ta.add_argument("--set", nargs="*")
    ta.add_argument("--evidence"); ta.set_defaults(fn=cmd_transition_add)

    an = sub.add_parser("answer"); an.add_argument("model"); an.add_argument("id")
    an.add_argument("value")
    an.add_argument("--section", default="constraints", choices=["constraints", "outcomes"])
    an.set_defaults(fn=cmd_answer)

    sh = sub.add_parser("show"); sh.add_argument("model"); sh.set_defaults(fn=cmd_show)

    rw = sub.add_parser("rows"); rw.add_argument("result")
    rw.add_argument("--env", type=int, default=0)
    rw.add_argument("--no-state", action="store_true", dest="no_state")
    rw.add_argument("--status"); rw.add_argument("--limit", type=int, default=50)
    rw.set_defaults(fn=cmd_rows)

    re_ = sub.add_parser("result"); re_.add_argument("result")
    re_.add_argument("--env", type=int, default=0); re_.set_defaults(fn=cmd_result)

    b = sub.add_parser("build"); b.add_argument("model"); b.add_argument("--root", default=".")
    b.add_argument("--env", type=int, default=0); b.set_defaults(fn=cmd_build)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

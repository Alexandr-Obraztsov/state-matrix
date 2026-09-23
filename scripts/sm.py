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


def result_path(model):
    return os.path.normpath(os.path.join(
        os.path.dirname(model) or ".", "..", "runs",
        os.path.basename(model).replace(".states.json", "") + ".json"))


def ref_ok(text, model_path, root):
    return validate.check_ref(text, store.load(model_path).get("source", ""), root)


def ref_hint(why):
    """Подсказка по существу ошибки, а не одна на все случаи."""
    if "пустое" in why:
        return "откуда это взято: раздел спеки, цитата, ссылка, номер задачи"
    return "сослался на файл репозитория — место в нём должно существовать"


# ---------- база знаний ----------

import kb


def project_root(model):
    """Корень проекта: модель лежит в <корень>/.states/models/."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(model))))


def cmd_cases(a):
    """Корнер-кейсы для вида параметра. Обращаться необязательно, но полезно."""
    kinds = kb.merged(project_root(a.model))
    if not a.kind:
        print("виды параметров в базе знаний:\n")
        for k in kinds:
            own = "  [своё]" if k.get("own") else ""
            aka = ", ".join(k.get("aka") or [])
            print(f"  {k['kind']:14} {len(k['cases'])} кейсов{own}"
                  + (f"   ({aka})" if aka else ""))
        print("\nкейсы вида: sm.py cases <модель> --kind строка")
        return
    q = a.kind.lower()
    hit = next((k for k in kinds
                if k["kind"] == q or q in [x.lower() for x in (k.get("aka") or [])]), None)
    if not hit:
        die(f"вида «{a.kind}» в базе нет",
            "список: sm.py cases <модель>; завести: sm.py learn <модель> --kind … --case …")
    print(f"{hit['kind']} — {len(hit['cases'])} корнер-кейсов")
    if hit.get("desc"):
        print(hit["desc"])
    print()
    for c in hit["cases"]:
        own = "  [своё]" if c.get("own") else ""
        print(f"  {c['case']}{own}")
        print(f"      {c.get('why','')}")


def cmd_learn(a):
    """Дописать корнер-кейс в базу знаний проекта."""
    root = project_root(a.model)
    try:
        if a.aka:
            kb.upsert_kind(root, a.kind, aka=a.aka)
        kb.add_case(root, a.kind, a.case, a.why or "")
    except kb.KBError as e:
        die(str(e))
    print(f"«{a.kind}» ← «{a.case}»")
    print(f"  записано в {kb.project_file(root)}; будет подсказываться в этом проекте впредь")


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
    """Параметр целиком: описание, ссылка, все значения и объединение в классы."""
    if not a.desc:
        die("не указан --desc", "что это за вход — одной фразой")
    if not a.frm:
        die("не указан --from",
            "откуда параметр: раздел спеки, цитата, ссылка, номер задачи")
    if not a.all_values:
        die("не указаны --all-values",
            "перечисли ВСЕ значения из спеки, включая корнер-кейсы")
    m = load(a.model)
    ok, why = ref_ok(a.frm, a.model, a.root)
    if not ok:
        die(f"--from не подтверждается: {why}", ref_hint(why))
    values = a.values or list(a.all_values)
    extra = [v for v in a.all_values if v not in values]
    if extra and not a.grouping:
        die(f"{len(a.all_values)} значений свёрнуто в {len(values)} классов без объяснения",
            f"нужен --grouping: почему они дают один исход. вне классов: {', '.join(extra[:8])}")
    m.setdefault("params", {})
    if a.name in m["params"] and not a.force:
        die(f"параметр «{a.name}» уже есть", "перезаписать: --force")
    p = {"desc": a.desc, "from": a.frm,
         "all_values": list(a.all_values), "values": values}
    if a.grouping:
        p["grouping"] = a.grouping
    if a.special:
        p["special"] = list(a.special)
    m["params"][a.name] = p
    store.save(a.model, m)
    if extra:
        print(f"«{a.name}»: {len(a.all_values)} значений → {len(values)} классов")
        print(f"  основание: {a.grouping}")
    else:
        print(f"«{a.name}»: {len(values)} значений")
    if a.special:
        print(f"  вне матрицы, по одному: {', '.join(a.special)}")
    print(f"  параметров всего: {len(m['params'])}")



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



# ---------- этап 2: значения ----------


# ---------- этап 3: состояния ----------

def cmd_state_add(a):
    """Состояние интерфейса: имя, что видно, ссылка. Условий нет — привязка
    к строкам матрицы делается отдельно, после свёртки."""
    m = load(a.model)
    if not a.desc:
        die("нет --desc", "что пользователь видит в этом состоянии")
    if not a.evidence:
        die("нет --evidence",
            "откуда состояние: раздел спеки, цитата, ссылка, номер задачи")
    ok, why = ref_ok(a.evidence, a.model, a.root)
    if not ok:
        die(f"--evidence не подтверждается: {why}", ref_hint(why))
    if any(s["name"] == a.name for s in (m.get("states") or [])):
        die(f"состояние «{a.name}» уже есть")
    m.setdefault("states", []).append(
        {"name": a.name, "desc": a.desc, "evidence": a.evidence})
    store.save(a.model, m)
    print(f"«{a.name}» — состояний всего {len(m['states'])}")



def cmd_state_rm(a):
    m = load(a.model)
    before = len(m.get("states") or [])
    m["states"] = [s for s in (m.get("states") or []) if s.get("name") != a.name]
    if len(m["states"]) == before:
        die(f"состояния «{a.name}» нет")
    m["assignments"] = {k: v for k, v in (m.get("assignments") or {}).items()
                        if v != a.name}
    store.save(a.model, m)
    print(f"«{a.name}» убрано вместе с его привязками")


def cmd_assign(a):
    """Привязать состояние к строкам матрицы по их номерам из последней сборки."""
    m = load(a.model)
    if not any(s["name"] == a.state for s in (m.get("states") or [])):
        die(f"состояния «{a.state}» нет",
            "сначала: sm.py state add … --name \"" + a.state + "\" --desc … --evidence …")
    res = store.load(result_path(a.model))
    if not res:
        die("матрица ещё не собрана", f"сначала: sm.py build {a.model}")
    by_id = {r["id"]: r["key"] for r in res["rows"]}
    unknown = [r for r in a.rows if r not in by_id]
    if unknown:
        die(f"нет таких строк: {', '.join(unknown)}",
            f"есть r000…r{len(res['rows'])-1:03d}; посмотреть: sm.py rows")
    m.setdefault("assignments", {})
    for rid in a.rows:
        m["assignments"][by_id[rid]] = a.state
    store.save(a.model, m)
    left = sum(1 for r in res["rows"]
               if r["id"] not in a.rows and not r["state"])
    print(f"«{a.state}» ← {len(a.rows)} строк: {', '.join(a.rows)}")
    print(f"  без состояния осталось примерно {left}; пересобери: sm.py build")



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
        die(f"--evidence не подтверждается: {why}", ref_hint(why))
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
    """Markdown-таблица: её можно отдать пользователю как есть, не переписывая."""
    out = ["| " + " | ".join(cols) + " | состояние |",
           "|" + "---|" * (len(cols) + 1)]
    for r in rows:
        cell = lambda v: "∗" if v == "*" else str(v)
        out.append("| " + " | ".join(cell(r["values"][c]) for c in cols)
                   + " | " + (r["state"] or "**?**") + " |")
    return "\n".join(out)


def show_result(res):
    """Вывод делится надвое: верх можно отдать пользователю как есть,
    низ — служебный, для назначения состояний."""
    c = res["counts"]
    print(f"**{c['total']} комбинаций свелись к {c['collapsed']} строкам.**\n")
    print(table(res["param_order"], res["rows"]))
    if res["specials"]:
        print("\nОтдельно проверить: "
              + ", ".join(f"`{x['param']} = {x['value']}`" for x in res["specials"]) + ".")
    if c["no_state"]:
        print(f"\n**Без состояния: {c['no_state']} "
              f"{'строка' if c['no_state'] == 1 else 'строк'}** — отмечены «?».")
    block = [f for f in res["findings"] if f["severity"] == "block"]
    for f in block:
        print("\n" + f["message"])

    print("\n--- служебное, пользователю не показывать ---")
    print(f"{res['system']}  ·  {res['source']}")
    print(f"воронка: {c['total']} → {c['valid']} → {c['collapsed']} (+{c['specials']} спец)")
    for st in res["states"]:
        print(f"  {st['rows']:3}  {st['name']}")
    if c["no_state"]:
        ids = [r["id"] for r in res["rows"] if not r["state"]]
        print(f"строки без состояния: {', '.join(ids)}")
        print("  назначить: sm_assign(state=…, rows=[…])")
        print("  либо запретить правилом, либо признать дырой в спеке")


def cmd_build(a):
    m = load(a.model)
    if not (m.get("params") or {}):
        die("в модели нет параметров",
            f"объявить: sm.py param add {a.model} --name … --all-values …")
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
    store.save(result_path(a.model), res)
    show_result(res)


def cmd_rows(a):
    res = store.load(result_path(a.model))
    if not res:
        die("матрица ещё не собрана", f"сначала: sm.py build {a.model}")
    rows = [r for r in res["rows"] if not r["state"]] if a.no_state else res["rows"]
    print(f"{len(rows)} строк из {len(res['rows'])}\n")
    for r in rows[:a.limit]:
        vv = ", ".join(f"{k}={v}" for k, v in r["values"].items() if v != "*")
        print(f"  {r['id']}  {vv}")
        if r["covers"] > 1:
            print(f"      покрывает {r['covers']} комбинаций")



def main():
    ap = argparse.ArgumentParser(prog="sm.py")
    ap.add_argument("--root", default=".", help="корень репозитория для проверки ссылок")
    sub = ap.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("init"); i.add_argument("model")
    i.add_argument("--system", required=True); i.add_argument("--source", required=True)
    i.add_argument("--force", action="store_true"); i.set_defaults(fn=cmd_init)

    p = sub.add_parser("param").add_subparsers(dest="x", required=True)
    pa = p.add_parser("add"); pa.add_argument("model")
    pa.add_argument("--name", required=True)
    pa.add_argument("--desc"); pa.add_argument("--from", dest="frm")
    pa.add_argument("--all-values", nargs="+", dest="all_values")
    pa.add_argument("--values", nargs="*"); pa.add_argument("--grouping")
    pa.add_argument("--special", nargs="*")
    pa.add_argument("--force", action="store_true"); pa.set_defaults(fn=cmd_param_add)
    pr = p.add_parser("rm"); pr.add_argument("model"); pr.add_argument("name")
    pr.set_defaults(fn=cmd_param_rm)

    ex = sub.add_parser("exclude"); ex.add_argument("model"); ex.add_argument("name")
    ex.add_argument("reason"); ex.set_defaults(fn=cmd_exclude)

    st = sub.add_parser("state").add_subparsers(dest="x", required=True)
    sa = st.add_parser("add"); sa.add_argument("model")
    sa.add_argument("--name", required=True)
    sa.add_argument("--desc"); sa.add_argument("--evidence"); sa.set_defaults(fn=cmd_state_add)
    sr = st.add_parser("rm"); sr.add_argument("model"); sr.add_argument("name")
    sr.set_defaults(fn=cmd_state_rm)

    asg = sub.add_parser("assign"); asg.add_argument("model")
    asg.add_argument("--state", required=True)
    asg.add_argument("--rows", nargs="+", required=True)
    asg.set_defaults(fn=cmd_assign)

    r = sub.add_parser("rule").add_subparsers(dest="x", required=True)
    ra = r.add_parser("add"); ra.add_argument("model"); ra.add_argument("--id", required=True)
    ra.add_argument("--forbid", nargs="*"); ra.add_argument("--when", nargs="*")
    ra.add_argument("--irrelevant", nargs="*"); ra.add_argument("--evidence")
    ra.add_argument("--desc"); ra.set_defaults(fn=cmd_rule_add)
    rr = r.add_parser("rm"); rr.add_argument("model"); rr.add_argument("id")
    rr.set_defaults(fn=cmd_rule_rm)

    kc = sub.add_parser("cases"); kc.add_argument("model"); kc.add_argument("--kind")
    kc.set_defaults(fn=cmd_cases)
    kl = sub.add_parser("learn"); kl.add_argument("model")
    kl.add_argument("--kind", required=True); kl.add_argument("--case", required=True)
    kl.add_argument("--why"); kl.add_argument("--aka", nargs="*")
    kl.set_defaults(fn=cmd_learn)

    rw = sub.add_parser("rows"); rw.add_argument("model")
    rw.add_argument("--no-state", action="store_true", dest="no_state")
    rw.add_argument("--limit", type=int, default=50); rw.set_defaults(fn=cmd_rows)
    b = sub.add_parser("build"); b.add_argument("model"); b.set_defaults(fn=cmd_build)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

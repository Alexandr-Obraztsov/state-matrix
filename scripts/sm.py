#!/usr/bin/env python3
"""Единственный способ изменить модель. Агент не редактирует YAML руками:
он вызывает эти команды, и каждая отказывает, если протокол нарушен.

Протокол добавления параметра:
  1. sm.py catalog <модель> <имя> --type <тип>      ← ОБЯЗАТЕЛЬНО первым
  2. ответить на все вопросы семантики
  3. sm.py param add ... -a q=ответ ...             ← иначе отказ
"""
import os, sys, json, argparse, datetime
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CATALOG = os.path.join(ROOT, "catalog", "default.json")


def die(msg, hint=""):
    print(f"ОТКАЗ: {msg}", file=sys.stderr)
    if hint:
        print(f"  {hint}", file=sys.stderr)
    sys.exit(2)


def load_model(p):
    if not os.path.exists(p):
        return {}
    return store.load(p) or {}


def save_model(p, m):
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    store.save(p, m)


def ledger_path(model):
    d = os.path.join(os.path.dirname(model) or ".", ".session")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, os.path.basename(model) + ".json")


def ledger(model):
    p = ledger_path(model)
    return json.load(open(p)) if os.path.exists(p) else {"lookups": {}}


def save_ledger(model, L):
    json.dump(L, open(ledger_path(model), "w"), ensure_ascii=False, indent=1)


def catalogs(project_dir):
    out = store.load(DEFAULT_CATALOG) or []
    local = os.path.join(project_dir, "catalog.json")
    if os.path.exists(local):
        out = (store.load(local) or []) + out
    return out


def find(cat, name, type_):
    exact, loose = [], []
    for c in cat:
        m = c.get("matches") or {}
        if name in (m.get("names") or []):
            exact.append(c)
        elif type_ and type_ in (m.get("types") or []):
            loose.append(c)
    return exact, loose


# ---------- команды ----------

def cmd_catalog(a):
    cat = catalogs(os.path.dirname(a.model) or ".")
    exact, loose = find(cat, a.name, a.type)
    L = ledger(a.model)
    hit = (exact or loose or [None])[0]

    print(f"# корзина для «{a.name}» (тип {a.type})")
    if exact:
        print(f"\nТОЧНОЕ СОВПАДЕНИЕ: {hit['id']}@{hit.get('version',1)}")
    elif loose:
        print(f"\nПОХОЖЕ: {hit['id']}@{hit.get('version',1)} — подтверди или заведи новую семантику")
    else:
        print("\nСОВПАДЕНИЙ НЕТ — семантика новая, заведи её командой `catalog new`")

    qs = (hit or {}).get("questions") or []
    if hit:
        print(f"  значения по умолчанию : {', '.join(map(str, hit.get('values', [])))}")
        print(f"  вне матрицы           : {', '.join(map(str, hit.get('special', [])))}")
        for sn in (hit.get("seen") or [])[-2:]:
            print(f"  раньше здесь          : {sn.get('where')} → {sn.get('values')}")
    print(f"\nОБЯЗАТЕЛЬНЫЕ ВОПРОСЫ ({len(qs)}) — без ответа на каждый параметр не добавится:")
    for q in qs:
        print(f"  -a {q['id']}=\"…\"   {q['ask']}")
    if not qs:
        print("  (у этой семантики вопросов нет)")

    L["lookups"][a.name] = {"catalog": (hit or {}).get("id"),
                            "questions": [q["id"] for q in qs],
                            "at": datetime.datetime.now().isoformat(timespec="seconds")}
    save_ledger(a.model, L)
    print(f"\nзапрос записан; теперь можно: sm.py param add {a.model} --name {a.name} …")


def cmd_param_add(a):
    L = ledger(a.model)
    look = L["lookups"].get(a.name)
    if not look:
        die(f"корзина для «{a.name}» не запрашивалась",
            f"сначала: sm.py catalog {a.model} {a.name} --type {a.type}")
    ans = dict(x.split("=", 1) for x in (a.answer or []))
    missing = [q for q in look["questions"] if q not in ans]
    if missing:
        die(f"нет ответов на вопросы семантики: {', '.join(missing)}",
            "ответить: -a <вопрос>=\"…\" по каждому, либо -a <вопрос>=неизвестно")
    if not a.frm:
        die("не указан --from", "источник значений обязателен: file:line")
    if not a.values:
        die("не указаны --values", "классы значений выводятся из ответов, но задаются явно")

    m = load_model(a.model)
    m.setdefault("params", {})
    if a.name in m["params"] and not a.force:
        die(f"параметр «{a.name}» уже есть", "перезаписать: --force")
    p = {"type": a.type, "values": a.values, "from": a.frm}
    if a.desc: p["desc"] = a.desc
    if look.get("catalog"): p["catalog"] = look["catalog"]
    if a.special: p["special"] = a.special
    if a.env: p["env"] = True
    p["answers"] = ans
    m["params"][a.name] = p
    save_model(a.model, m)
    print(f"параметр «{a.name}» добавлен: {len(a.values)} значений"
          f"{', ' + str(len(a.special)) + ' вне матрицы' if a.special else ''}"
          f"{', окружение' if a.env else ''}")


def cmd_exclude(a):
    m = load_model(a.model)
    m.setdefault("excluded", {})[a.name] = a.reason
    save_model(a.model, m)
    print(f"«{a.name}» исключён: {a.reason}")


def cmd_rule_add(a):
    m = load_model(a.model)
    P = m.get("params") or {}
    if not P:
        die("в модели нет параметров", "сначала добавь параметры")
    def parse(pairs):
        d = {}
        for x in pairs or []:
            k, v = x.split("=", 1)
            vals = v.split(",")
            if k not in P: die(f"неизвестный параметр «{k}»")
            for z in vals:
                if z not in [str(y) for y in P[k]["values"]]:
                    die(f"значение «{z}» отсутствует в {k}.values")
            d[k] = vals if len(vals) > 1 else vals[0]
        return d
    if not a.evidence:
        die("нет --evidence", "правило без основания не принимается")
    has_ref = ":" in a.evidence and any(ch.isdigit() for ch in a.evidence.split(":")[-1][:4])
    status = "proven" if has_ref and not a.assumed else "assumed"
    if status == "assumed" and not a.ask:
        die("правило без ссылки file:line становится assumed и требует --ask",
            "сформулируй вопрос человеку одной фразой")
    r = {"id": a.id, "evidence": a.evidence, "status": status}
    if a.desc: r["desc"] = a.desc
    if a.ask: r["ask"] = a.ask
    if a.forbid:
        r["forbid"] = parse(a.forbid)
    elif a.irrelevant:
        r["when"] = parse(a.when)
        r["irrelevant"] = a.irrelevant
    else:
        die("нужно либо --forbid, либо --irrelevant")
    m.setdefault("constraints", []).append(r)
    save_model(a.model, m)
    print(f"правило {a.id} добавлено со статусом {status}")


def cmd_state_add(a):
    m = load_model(a.model)
    P = m.get("params") or {}
    d = {}
    for x in a.when or []:
        k, v = x.split("=", 1)
        if k not in P: die(f"неизвестный параметр «{k}»")
        vals = v.split(",")
        d[k] = vals if len(vals) > 1 else vals[0]
    if not a.evidence:
        die("нет --evidence", "состояние должно ссылаться на код или спеку")
    st = {"name": a.name, "when": d, "evidence": a.evidence}
    if a.desc: st["desc"] = a.desc
    m.setdefault("states", []).append(st)
    save_model(a.model, m)
    print(f"состояние «{a.name}» добавлено; условие: {d or 'всегда'}")


def cmd_build(a):
    import subprocess
    sc = lambda n: os.path.join(ROOT, "scripts", n)
    name = os.path.splitext(os.path.basename(a.model))[0].replace(".states", "")
    out = os.path.join(os.path.dirname(a.model) or ".", "..", "runs", name + ".json")
    out = os.path.normpath(out)
    steps = [["python3", sc("verify.py"), a.model, "--root", a.root],
             ["python3", sc("validate.py"), a.model],
             ["python3", sc("engine.py"), a.model, "-a",
              os.path.join(os.path.dirname(a.model) or ".", "..", "answers.json"), "-o", out]]
    for cmd in steps:
        r = subprocess.run(cmd, text=True)
        if r.returncode:
            die(f"шаг не прошёл: {' '.join(os.path.basename(x) for x in cmd[:2])}",
                "конвейер остановлен, модель не собрана")
    print()
    subprocess.run(["python3", sc("report_md.py"), out])


def main():
    ap = argparse.ArgumentParser(prog="sm.py")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("catalog", help="ОБЯЗАТЕЛЬНЫЙ первый шаг для параметра")
    c.add_argument("model"); c.add_argument("name")
    c.add_argument("--type", required=True)
    c.set_defaults(fn=cmd_catalog)

    p = sub.add_parser("param").add_subparsers(dest="x", required=True)
    pa = p.add_parser("add")
    pa.add_argument("model"); pa.add_argument("--name", required=True)
    pa.add_argument("--type", required=True); pa.add_argument("--values", nargs="+")
    pa.add_argument("--from", dest="frm"); pa.add_argument("--desc")
    pa.add_argument("--special", nargs="*"); pa.add_argument("--env", action="store_true")
    pa.add_argument("-a", "--answer", action="append")
    pa.add_argument("--force", action="store_true")
    pa.set_defaults(fn=cmd_param_add)

    e = sub.add_parser("exclude")
    e.add_argument("model"); e.add_argument("name"); e.add_argument("reason")
    e.set_defaults(fn=cmd_exclude)

    r = sub.add_parser("rule").add_subparsers(dest="x", required=True)
    ra = r.add_parser("add")
    ra.add_argument("model"); ra.add_argument("--id", required=True)
    ra.add_argument("--forbid", nargs="*"); ra.add_argument("--when", nargs="*")
    ra.add_argument("--irrelevant", nargs="*")
    ra.add_argument("--evidence"); ra.add_argument("--desc"); ra.add_argument("--ask")
    ra.add_argument("--assumed", action="store_true")
    ra.set_defaults(fn=cmd_rule_add)

    st = sub.add_parser("state").add_subparsers(dest="x", required=True)
    sa = st.add_parser("add")
    sa.add_argument("model"); sa.add_argument("--name", required=True)
    sa.add_argument("--when", nargs="*"); sa.add_argument("--desc")
    sa.add_argument("--evidence")
    sa.set_defaults(fn=cmd_state_add)

    b = sub.add_parser("build")
    b.add_argument("model"); b.add_argument("--root", default=".")
    b.set_defaults(fn=cmd_build)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

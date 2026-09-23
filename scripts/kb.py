#!/usr/bin/env python3
"""База знаний: базовая часть плагина плюс проектная.

Базовая (knowledge/base.json) никогда не переписывается — она обновляется
вместе с плагином. Дописанное ложится в проект (.states/knowledge.json).
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "knowledge", "base.json")
SOURCES = os.path.join(ROOT, "knowledge", "sources.json")


class KBError(Exception):
    pass


def project_file(project_root):
    return os.path.join(project_root, ".states", "knowledge.json")


def _copy(x):
    return json.loads(json.dumps(x))


def load_project(project_root):
    return store.load(project_file(project_root)) or []


def save_project(project_root, data):
    store.save(project_file(project_root), data)


def merged(project_root):
    """Итоговая база: виды в порядке базы, затем свои. У кейса пометка own,
    у скрытых кейсов плагина — отдельный список hidden для возврата."""
    base = _copy(store.load(BASE) or [])
    out = {k["kind"]: dict(k, own=False, hidden=[]) for k in base}
    for k in base:
        for c in out[k["kind"]]["cases"]:
            c["own"] = False
    for p in load_project(project_root):
        name = p["kind"]
        if name not in out:
            out[name] = {"kind": name, "desc": p.get("desc", ""), "aka": [],
                         "cases": [], "own": True, "hidden": []}
        k = out[name]
        if p.get("desc"):
            k["desc"] = p["desc"]
        for a in p.get("aka") or []:
            if a not in k.setdefault("aka", []):
                k["aka"].append(a)
        hidden = set(p.get("hidden") or [])
        k["hidden"] = [c for c in k["cases"] if c["case"] in hidden and not c["own"]]
        k["cases"] = [c for c in k["cases"] if c["case"] not in hidden]
        have = {c["case"] for c in k["cases"]}
        for c in p.get("cases") or []:
            if c["case"] not in have:
                k["cases"].append(dict(c, own=True))
                have.add(c["case"])
    return list(out.values())


def _entry(data, kind):
    e = next((k for k in data if k["kind"] == kind), None)
    if e is None:
        e = {"kind": kind, "cases": []}
        data.append(e)
    e.setdefault("cases", [])
    return e


def _base_cases(kind):
    k = next((x for x in (store.load(BASE) or []) if x["kind"] == kind), None)
    return {c["case"] for c in (k or {}).get("cases", [])}


def _visible(project_root, kind):
    k = next((x for x in merged(project_root) if x["kind"] == kind), None)
    return {c["case"] for c in (k or {}).get("cases", [])}


def add_case(project_root, kind, case, why=""):
    case = (case or "").strip()
    if not kind or not case:
        raise KBError("нужны вид и сам кейс")
    if case in _visible(project_root, kind):
        raise KBError(f"кейс «{case}» у вида «{kind}» уже есть")
    data = load_project(project_root)
    e = _entry(data, kind)
    if case in (e.get("hidden") or []):
        e["hidden"].remove(case)          # был скрыт — просто возвращаем
    else:
        e["cases"].append({"case": case, "why": (why or "").strip()})
    save_project(project_root, data)



def upsert_kind(project_root, kind, desc=None, aka=None):
    kind = (kind or "").strip()
    if not kind:
        raise KBError("нужно название вида")
    data = load_project(project_root)
    e = _entry(data, kind)
    if desc is not None:
        e["desc"] = desc.strip()
    if aka:
        e["aka"] = sorted(set((e.get("aka") or []) + [a.strip() for a in aka if a.strip()]))
    save_project(project_root, data)


def sources():
    return store.load(SOURCES) or {}

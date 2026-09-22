#!/usr/bin/env python3
"""state-matrix engine: модель -> result.json. Детерминирован, без ИИ."""
import sys, os, json, itertools, hashlib, datetime, argparse
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import store
from collections import deque

from store import CEILING
UNREACHABLE_GUARD = 0.5


# ---------- утилиты ----------

def as_list(v):
    return v if isinstance(v, list) else [v]


def matches(row, cond):
    for k, v in (cond or {}).items():
        if k not in row or row[k] not in as_list(v):
            return False
    return True


def rule_sentence(c, params):
    """Правило по-русски: что оно делает с матрицей."""
    def vals(v):
        return " или ".join(f"«{x}»" for x in (v if isinstance(v, list) else [v]))
    if "forbid" in c:
        cond = ", ".join(f"{k} = {vals(v)}" for k, v in c["forbid"].items())
        return {"kind": "запрет", "what": f"комбинация {cond} невозможна",
                "effect": "строки вычёркиваются из матрицы"}
    w = c.get("when") or {}
    cond = ", ".join(f"{k} = {vals(v)}" for k, v in w.items()) or "всегда"
    ps = ", ".join(c["irrelevant"])
    return {"kind": "схлопывание", "what": f"при {cond} значения {ps} на исход не влияют",
            "effect": f"колонки {ps} сливаются в «∗»"}


def rule_label(c):
    if "forbid" in c:
        return "forbid " + ", ".join(f"{k}={v}" for k, v in c["forbid"].items())
    w = c.get("when") or {}
    w = ", ".join(f"{k}={v}" for k, v in w.items()) or "всегда"
    return f"{w} → не важно: {', '.join(c['irrelevant'])}"


def key(row):
    return "|".join(f"{k}={row[k]}" for k in sorted(row))


# ---------- построение матрицы ----------

def cartesian(params):
    names = list(params)
    axes = [params[n]["values"] for n in names]
    total = 1
    for a in axes:
        total *= len(a)
    return names, total, [dict(zip(names, c)) for c in itertools.product(*axes)]


def apply_forbid(rows, forbids):
    funnel, kept = [], rows
    for c in forbids:
        before = len(kept)
        kept = [r for r in kept if not matches(r, c["forbid"])]
        funnel.append({"rule": rule_label(c), "evidence": c.get("evidence", "—"),
                       "removed": before - len(kept)})
    return kept, funnel


def collapse(valid, irrelevants):
    """Схлопывает незначащие колонки. Хранит, какие комбинации покрыла строка."""
    groups, order, why = {}, [], {}
    for r in valid:
        v, used = dict(r), []
        for c in irrelevants:
            if matches(r, c.get("when") or {}):
                for p in c["irrelevant"]:
                    if v[p] != "*":
                        v[p] = "*"
                        used.append(c)
        k = key(v)
        if k not in groups:
            groups[k] = {"values": v, "covered": []}
            order.append(k)
            why[k] = used
        groups[k]["covered"].append(r)

    out = []
    for i, k in enumerate(order):
        g = groups[k]
        starred = [p for p, x in g["values"].items() if x == "*"]
        detail = {p: sorted({str(c[p]) for c in g["covered"]}) for p in starred}
        out.append({
            "id": f"r{i:04d}",
            "values": g["values"],
            "covers": len(g["covered"]),
            "collapsed": detail,
            "rules": [{"rule": rule_label(c), "evidence": c.get("evidence", "—")}
                      for c in {id(x): x for x in why[k]}.values()],
            "raw": g["covered"],
        })
    return out


# ---------- достижимость ----------

def step(row, t):
    nxt = dict(row)
    for k, v in t["set"].items():
        nxt[k] = (not row[v[1:]]) if isinstance(v, str) and v.startswith("!") else v
    return nxt


def reachability(model, valid):
    trans = model.get("transitions") or []
    inits = model.get("initial")
    if not inits or not trans:
        return None
    inits = inits if isinstance(inits, list) else [inits]

    index = {key(r): r for r in valid}
    bad_init = [i for i in inits if key(i) not in index]
    starts = [key(i) for i in inits if key(i) in index]

    parent, seen, q = {}, set(starts), deque(starts)
    invalid_edges, nondet = [], []
    outdeg = {}
    while q:
        ck = q.popleft()
        cur = index[ck]
        outdeg.setdefault(ck, 0)
        for t in trans:
            if not matches(cur, t.get("when")):
                continue
            nxt = step(cur, t)
            nk = key(nxt)
            if nk not in index:
                invalid_edges.append({"from": cur, "event": t["event"], "to": nxt,
                                      "evidence": t.get("evidence", "—")})
                continue
            outdeg[ck] += 1
            if nk not in seen:
                seen.add(nk)
                parent[nk] = (ck, t)
                q.append(nk)

    # кратчайший путь от старта: событие, что изменилось, где это в коде
    paths = {}
    for k in seen:
        chain, cur = [], k
        while cur in parent:
            prev, t = parent[cur]
            a, b = index[prev], index[cur]
            chain.append({
                "event": t["event"],
                "evidence": t.get("evidence", "—"),
                "changes": {p: [a[p], b[p]] for p in a if a[p] != b[p]},
            })
            cur = prev
        paths[k] = list(reversed(chain))

    for r in valid:                       # недетерминизм
        by_event = {}
        for t in trans:
            if matches(r, t.get("when")):
                by_event.setdefault(t["event"], set()).add(key(step(r, t)))
        for ev, outs in by_event.items():
            if len(outs) > 1:
                nondet.append({"row": r, "event": ev})

    unreachable = [r for r in valid if key(r) not in seen]
    dead = [index[k] for k, d in outdeg.items() if d == 0]
    return {"reachable": seen, "paths": paths, "unreachable": unreachable,
            "dead_ends": dead, "nondet": nondet, "invalid_edges": invalid_edges,
            "bad_initial": bad_init, "initial_keys": starts}


# ---------- детекторы ----------

def overlapping_irrelevant(irrelevants, valid):
    """Два правила схлопывания, применимых к одной строке -> порядок проверок не определён."""
    out = []
    for i in range(len(irrelevants)):
        for j in range(i + 1, len(irrelevants)):
            a, b = irrelevants[i], irrelevants[j]
            hits = [r for r in valid
                    if matches(r, a.get("when") or {}) and matches(r, b.get("when") or {})]
            if hits and (a.get("when") or {}) and (b.get("when") or {}):
                out.append({"a": rule_label(a), "a_ev": a.get("evidence", "—"),
                            "b": rule_label(b), "b_ev": b.get("evidence", "—"),
                            "rows": len(hits), "example": hits[0]})
    return out


def state_name(st):
    """Имя состояния; для старых моделей на outcomes — их behavior."""
    return st.get("name") or st.get("behavior") or "—"


def match_state(row, states):
    """Первое подходящее именованное состояние. Порядок в модели значим."""
    for st in states:
        if matches(row, st.get("when") or st.get("match") or {}):
            return st
    return None


# ---------- сборка ----------

def advise(params, matrix_len, model, cons):
    """Вклад параметров в размер матрицы и самые дешёвые способы ужаться."""
    changed = set()
    for t in (model.get("transitions") or []):
        changed |= set((t.get("set") or {}).keys())
    ruled = set()
    for c in cons:
        ruled |= set((c.get("forbid") or {}).keys())
        ruled |= set((c.get("when") or {}).keys())
        ruled |= set(c.get("irrelevant") or [])
    contrib = []
    for n, p in params.items():
        f = len(p["values"])
        contrib.append({"param": n, "factor": f,
                        "env_candidate": n not in changed and not p.get("env"),
                        "rows_if_env": matrix_len // f if f else matrix_len})
    contrib.sort(key=lambda c: (-c["factor"], c["param"]))
    cheapest = [f"пометить env: {c['param']} (×{c['factor']}) → {c['rows_if_env']} строк"
                for c in contrib if c["env_candidate"]][:3]
    return {"over": matrix_len > CEILING, "ceiling": CEILING,
            "contributions": contrib, "unruled": sorted(set(params) - ruled),
            "cheapest": cheapest}


def build_slice(model, answers, env_values):
    """Одна матрица для фиксированного окружения."""
    params = {n: v for n, v in model["params"].items() if not v.get("env")}
    names, total, rows = cartesian(params)
    for r in rows:
        r.update(env_values)

    cons = list(model.get("constraints") or [])
    for c in cons:                                  # ответы человека повышают статус
        rid = c.get("id")
        if rid and answers.get("constraints", {}).get(rid) == "proven":
            c["status"] = "proven"
            c["evidence"] = c.get("evidence", "") + "  [подтверждено человеком]"

    proven = [c for c in cons if c.get("status") == "proven"]
    assumed = [c for c in cons if c.get("status") != "proven"]
    forbids = [c for c in proven if "forbid" in c]
    irrel = [c for c in proven if "irrelevant" in c]

    valid, forbid_funnel = apply_forbid(rows, forbids)
    matrix = collapse(valid, irrel)

    # начальные состояния дополняются значениями окружения этого среза
    _m = dict(model)
    _init = model.get("initial")
    if _init:
        _init = _init if isinstance(_init, list) else [_init]
        seen_i, merged = set(), []
        for i in _init:
            j = dict(i); j.update(env_values)
            if key(j) not in seen_i:
                seen_i.add(key(j)); merged.append(j)
        _m["initial"] = merged
    reach = reachability(_m, valid)
    states = model.get("states") or model.get("outcomes") or []

    human = (answers.get("outcomes") or {})
    for m in matrix:
        hits = {state_name(x) if x else None
                for x in (match_state(r, states) for r in m["raw"])}
        o = match_state(m["values"], states)
        if o is None and len(hits) == 1:
            nm = next(iter(hits))
            o = next((x for x in states if state_name(x) == nm), None) if nm else None
        m["mixed"] = len(hits) > 1
        m["key"] = key(m["values"])
        m["state"] = state_name(o) if o else None
        m["outcome"] = (o or {}).get("desc") or (o or {}).get("behavior")
        m["outcome_evidence"] = (o or {}).get("evidence")
        m["status"] = "described" if o else "undefined"
        ans = human.get(key(m["values"]))
        if ans == "described":
            m["status"] = "described"
            m["outcome"] = m["outcome"] or "подтверждено человеком"
            m["outcome_evidence"] = "ответ в отчёте"
        elif ans == "contradictory":
            m["status"] = "contradictory"
            m["outcome_evidence"] = "помечено человеком как противоречие"
        if reach:
            ks = [key(r) for r in m["raw"]]
            hit = [k for k in ks if k in reach["reachable"]]
            m["reachable"] = bool(hit)
            m["path"] = reach["paths"].get(hit[0], []) if hit else None
            if not hit and ans is None:
                m["status"] = "unreachable"
        else:
            m["reachable"] = None
            m["path"] = None
        del m["raw"]

    specials = [{"param": n, "value": s, "id": f"s{i:03d}"}
                for i, (n, s) in enumerate(
                    (n, s) for n in names for s in params[n].get("special", []))]

    questions = []
    for i, c in enumerate(assumed):
        rid = c.get("id", f"q{i:03d}")
        hits = sum(1 for r in valid
                   if matches(r, c.get("forbid") or c.get("when") or {}))
        questions.append({"id": rid, "ask": c.get("ask", c.get("evidence", "—")),
                          "guess": rule_label(c), "evidence": c.get("evidence", "—"),
                          "cost_rows": hits, "answered": answers.get("constraints", {}).get(rid)})

    advice = advise(params, len(matrix), model, cons)

    state_stats = []
    for st in states:
        n = sum(1 for m in matrix if m.get("state") == state_name(st))
        state_stats.append({"name": state_name(st), "desc": st.get("desc"),
                            "when": st.get("when") or st.get("match") or {},
                            "evidence": st.get("evidence", "—"), "rows": n})
    no_state = [m for m in matrix if not m.get("state")]

    rules_out = []
    for c in cons:
        sent = rule_sentence(c, params)
        pool = rows if "forbid" in c else valid
        hits = sum(1 for r in pool if matches(r, c.get("forbid") or c.get("when") or {}))
        rules_out.append({"id": c.get("id"), "kind": sent["kind"], "what": sent["what"],
                          "effect": sent["effect"], "desc": c.get("desc"),
                          "evidence": c.get("evidence", "—"),
                          "status": c.get("status", "assumed"),
                          "ask": c.get("ask"), "rows": hits})

    funnel = [{"stage": "полное произведение", "count": total, "rules": []}]
    funnel.append({"stage": "после forbid", "count": len(valid), "rules": forbid_funnel})
    funnel.append({"stage": "после схлопывания", "count": len(matrix),
                   "rules": [{"rule": rule_label(c), "evidence": c.get("evidence", "—"),
                              "removed": None} for c in irrel]})
    funnel.append({"stage": "+ спецзначения", "count": len(matrix) + len(specials), "rules": []})

    findings = []
    if reach:
        pct = len(reach["unreachable"]) / max(len(valid), 1)
        if pct > UNREACHABLE_GUARD:
            findings.append({"class": "MODEL_INCOMPLETE", "severity": "block",
                             "message": f"недостижимо {pct:.0%} валидных комбинаций — "
                                        "раздел transitions неполон, достижимость не считаю"})
        else:
            for r in reach["unreachable"]:
                findings.append({"class": "UNREACHABLE", "severity": "warn", "row": r,
                                 "message": "комбинация валидна, но ни один путь событий в неё не ведёт"})
        for d in reach["dead_ends"]:
            findings.append({"class": "DEAD_END", "severity": "warn", "row": d,
                             "message": "из состояния нет ни одного перехода"})
        for n in reach["nondet"]:
            findings.append({"class": "NONDET", "severity": "block", "row": n["row"],
                             "message": f"событие «{n['event']}» ведёт из этого состояния в разные"})
        for e in reach["invalid_edges"]:
            findings.append({"class": "INVALID_EDGE", "severity": "block", "row": e["from"],
                             "message": f"«{e['event']}» ведёт в запрещённую комбинацию"})
        for b in reach["bad_initial"]:
            findings.append({"class": "BAD_INITIAL", "severity": "block", "row": b,
                             "message": "начальное состояние не проходит собственные ограничения"})

    for ov in overlapping_irrelevant(irrel, valid):
        findings.append({"class": "RULE_OVERLAP", "severity": "block", "row": ov["example"],
                         "message": f"два правила применимы одновременно к {ov['rows']} комбинациям "
                                    f"— порядок проверок не определён: «{ov['a']}» ({ov['a_ev']}) "
                                    f"и «{ov['b']}» ({ov['b_ev']})"})

    contra = [m for m in matrix if m["status"] == "contradictory"]
    if contra:
        findings.insert(0, {"class": "CONTRADICTORY", "severity": "block",
                            "message": f"{len(contra)} строк помечены человеком как противоречие",
                            "row_ids": [m["id"] for m in contra]})
    undef = [m for m in matrix if m["status"] == "undefined"]
    if undef:
        findings.append({"class": "UNDEFINED", "severity": "warn",
                         "message": f"{len(undef)} строк не отнесены ни к одному состоянию",
                         "row_ids": [m['id'] for m in undef][:200]})
    mixed = [m for m in matrix if m.get("mixed")]
    if mixed:
        findings.append({"class": "MIXED_STATE", "severity": "block",
                         "message": f"{len(mixed)} схлопнутых строк покрывают разные состояния — "
                                    "правило схлопывания слишком широкое",
                         "row_ids": [m["id"] for m in mixed][:200]})

    if advice["over"]:
        lines = [f"{len(matrix)} строк при потолке {CEILING}", "",
                 "вклад параметров:"]
        for c in advice["contributions"]:
            tail = (f"env-кандидат → {c['rows_if_env']} строк"
                    if c["env_candidate"] else "меняется переходами, env не подходит")
            lines.append(f"  {c['param']:14} ×{c['factor']}   {tail}")
        if advice["cheapest"]:
            lines += ["", "дешевле всего: " + "; ".join(advice["cheapest"])]
        if advice["unruled"]:
            lines += ["", "без единого правила: " + ", ".join(advice["unruled"])
                      + " — проверь, влияют ли они на исход вообще"]
        findings.insert(0, {"class": "CEILING", "severity": "block",
                            "message": "\n".join(lines)})

    return {
        "env": env_values,
        "funnel": funnel,
        "advice": advice,
        "rules": rules_out,
        "states": state_stats,
        "no_state": len(no_state),
        "questions": questions,
        "rows": matrix,
        "specials": specials,
        "findings": findings,
        "transitions": [{"event": t["event"], "when": t.get("when") or {},
                         "set": t["set"], "evidence": t.get("evidence", "—")}
                        for t in (model.get("transitions") or [])],
        "initial": _m.get("initial") if model.get("initial") else None,
        "counts": {"total": total, "valid": len(valid), "collapsed": len(matrix),
                   "specials": len(specials), "to_review": len(matrix) + len(specials),
                   "reachable": len(reach["reachable"]) if reach else None,
                   "undefined": len(undef)},
    }


def build(model, answers):
    params = model["params"]
    env_names = [n for n, v in params.items() if v.get("env")]
    state_names = [n for n in params if n not in env_names]
    combos = [dict(zip(env_names, c))
              for c in itertools.product(*[params[n]["values"] for n in env_names])] or [{}]

    # окружения, целиком запрещённые forbid-правилами, не порождают срез
    slices = []
    for env in combos:
        sl = build_slice(model, answers, env)
        if sl["counts"]["valid"] == 0:
            continue
        slices.append(sl)

    worst = max((s["counts"]["collapsed"] for s in slices), default=0)
    total_all = sum(s["counts"]["total"] for s in slices)
    return {
        "system": model["system"],
        "source": model.get("source", "—"),
        "mode": model.get("mode", "code"),
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "model_hash": hashlib.sha256(json.dumps(model, sort_keys=True,
                                                default=str).encode()).hexdigest()[:12],
        "ceiling": CEILING,
        "params": {n: params[n] for n in params},
        "excluded": model.get("excluded") or {},
        "param_order": state_names,
        "env_order": env_names,
        "slices": slices,
        "summary": {
            "environments": len(slices),
            "total": total_all,
            "worst_slice": worst,
            "over_ceiling": worst > CEILING,
            "findings": sum(len(s["findings"]) for s in slices),
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("-o", "--out")
    ap.add_argument("-a", "--answers")
    a = ap.parse_args()
    model = store.load(a.model)
    answers = {}
    if a.answers and os.path.exists(a.answers):
        answers = store.load(a.answers) or {}
    res = build(model, answers)
    text = json.dumps(res, ensure_ascii=False, indent=2, sort_keys=False)
    if a.out:
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        open(a.out, "w").write(text)
        s_ = res["summary"]
        print(f"{res['system']}: окружений {s_['environments']}, всего {s_['total']} комбинаций")
        for sl in res["slices"]:
            c = sl["counts"]
            env = ", ".join(f"{k}={v}" for k, v in sl["env"].items()) or "—"
            flag = "  !! ПОТОЛОК" if c["collapsed"] > res["ceiling"] else ""
            print(f"  [{env}]  {c['total']} → {c['valid']} → {c['collapsed']} "
                  f"(+{c['specials']}) = {c['to_review']}   находок {len(sl['findings'])}"
                  f"   достижимо {c['reachable']}{flag}")
        print(f"→ {a.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()

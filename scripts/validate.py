#!/usr/bin/env python3
"""Проверка модели: инварианты и ссылки. Код выхода 1, если есть ошибки."""
import os, re, sys, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store

# ссылка на раздел документа или на строку файла
SECTION = re.compile(r"([\w./-]+\.\w+):(§[\w.\-]+|\"[^\"]+\")")
LINE = re.compile(r"([\w./-]+\.\w+)?:(\d+)")


def resolve(ref_file, source, root):
    if not ref_file:
        return os.path.join(root, source)
    if os.path.isabs(ref_file):
        return ref_file
    near = os.path.join(os.path.dirname(os.path.join(root, source)),
                        os.path.basename(ref_file))
    return near if os.path.exists(near) else os.path.join(root, ref_file)


def check_ref(text, source, root):
    """-> (ok, сообщение). Ссылка обязана указывать на существующее место."""
    m = SECTION.search(str(text))
    if m:
        path = resolve(m.group(1), source, root)
        if not os.path.exists(path):
            return False, f"нет файла {os.path.basename(path)}"
        needle = m.group(2).strip('"')
        if needle not in open(path, encoding="utf-8").read():
            return False, f"раздела «{needle}» в {os.path.basename(path)} нет — ссылка выдумана"
        return True, ""
    m = LINE.search(str(text))
    if m:
        path = resolve(m.group(1), source, root)
        if not os.path.exists(path):
            return False, f"нет файла {os.path.basename(path)}"
        n = int(m.group(2))
        lines = open(path, encoding="utf-8").read().split("\n")
        if not (1 <= n <= len(lines)):
            return False, f"{os.path.basename(path)}: строки {n} нет (всего {len(lines)})"
        return True, ""
    return False, "нет ссылки вида spec.md:§3"


def check(path, root="."):
    m = store.load(path)
    if not isinstance(m, dict):
        return [f"{path}: это не модель"], []
    errs, warns = [], []
    P = m.get("params") or {}
    src = m.get("source", "")

    if not m.get("system"):
        errs.append("нет поля system")
    if not P:
        errs.append("нет параметров")

    def known(name, val, where):
        if name not in P:
            errs.append(f"{where}: неизвестный параметр «{name}»")
            return
        for v in (val if isinstance(val, list) else [val]):
            if v not in [str(y) for y in (P[name].get("values") or [])]:
                errs.append(f"{where}: значение «{v}» отсутствует у {name}")

    def ref(text, where):
        ok, why = check_ref(text, src, root)
        if not ok:
            errs.append(f"{where}: {why}")

    for n, p in P.items():
        if not p.get("desc"):
            errs.append(f"{n}: нет desc")
        if not p.get("from"):
            errs.append(f"{n}: нет from — не указано, откуда параметр")
        else:
            ref(p["from"], n)
        if not p.get("values"):
            errs.append(f"{n}: значения не заданы")
        av = p.get("all_values")
        if not av:
            errs.append(f"{n}: нет all_values — не перечислены все значения")
        elif [v for v in av if v not in (p.get("values") or [])] and not p.get("grouping"):
            errs.append(f"{n}: {len(av)} значений свёрнуто в "
                        f"{len(p.get('values') or [])} классов без объяснения")

    for i, c in enumerate(m.get("constraints") or []):
        w = f"правило {c.get('id') or i}"
        if not c.get("evidence"):
            errs.append(f"{w}: нет evidence")
        else:
            ref(c["evidence"], w)
        for k, v in (c.get("forbid") or {}).items():
            known(k, v, w)
        for k, v in (c.get("when") or {}).items():
            known(k, v, w)
        for x in (c.get("irrelevant") or []):
            if x not in P:
                errs.append(f"{w}: неизвестный параметр «{x}»")

    states = m.get("states") or []
    if not states:
        warns.append("нет ни одного состояния — матрица будет без исходов")
    seen = set()
    for i, st in enumerate(states):
        w = f"состояние «{st.get('name','?')}»"
        if not st.get("name"):
            errs.append(f"состояние {i}: нет name")
        if not st.get("desc"):
            errs.append(f"{w}: нет desc — что видит пользователь")
        if not st.get("evidence"):
            errs.append(f"{w}: нет evidence")
        else:
            ref(st["evidence"], w)
        if st.get("name") in seen:
            errs.append(f"{w}: имя повторяется")
        seen.add(st.get("name"))
        for k, v in (st.get("when") or {}).items():
            known(k, v, w)
        if not (st.get("when") or {}) and i < len(states) - 1:
            errs.append(f"{w}: условия нет, но оно не последнее — перекроет всё ниже")

    return errs, warns


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="+")
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    bad = 0
    for p in a.models:
        e, w = check(p, a.root)
        print(f"{p}: {'OK' if not e else str(len(e)) + ' ошибок'}"
              + (f", {len(w)} замечаний" if w else ""))
        for x in e:
            print("  ОШИБКА    " + x)
        for x in w:
            print("  замечание " + x)
        bad += len(e)
    sys.exit(1 if bad else 0)

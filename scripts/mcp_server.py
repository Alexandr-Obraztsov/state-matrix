#!/usr/bin/env python3
"""MCP-сервер state-matrix поверх stdio. Тонкая обёртка над sm.py: те же функции,
тот же код отказа. Протокол JSON-RPC 2.0 реализован вручную — зависимостей нет.

Отлаживать можно тем же CLI: любой тул соответствует подкоманде sm.py.
"""
import io, json, os, sys, contextlib, traceback
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sm  # noqa: E402

VERSION = "1.0.0"

S = lambda d: {"type": "string", "description": d}
SL = lambda d: {"type": "array", "items": {"type": "string"}, "description": d}
B = lambda d: {"type": "boolean", "description": d}


def tool(name, desc, props, required, fn, defaults=None):
    return {"name": name, "description": desc, "_fn": fn, "_defaults": defaults or {},
            "inputSchema": {"type": "object", "properties": props, "required": required}}


MODEL = S("путь к модели, например .states/models/Checkout.states.json")
ROOT = S("корень репозитория для проверки ссылок; по умолчанию текущий каталог")
REF = S("ссылка на место в спеке: docs/spec.md:§3. Проверяется — выдуманная не пройдёт")

TOOLS = [
    tool("sm_init",
         "Шаг 1. Завести модель по спецификации. Дальше прочитай спеку и ВСЁ, на что "
         "она ссылается — соседние документы, схемы, задачи в трекере — прежде чем "
         "объявлять параметры.",
         {"model": MODEL, "system": S("имя системы"), "source": S("путь к спецификации")},
         ["model", "system", "source"], sm.cmd_init, {"force": False, "root": "."}),

    tool("sm_param_add",
         "Шаг 2. Входной параметр целиком. all_values — ВСЕ значения из спеки, "
         "включая корнер-кейсы. values — классы после объединения, grouping — почему "
         "объединённые дают один исход. special — значения вне матрицы, они "
         "проверяются по одному и не умножают её. Объяви все параметры, какие нашёл, "
         "потом покажи их пользователю и спроси, все ли это.",
         {"model": MODEL, "name": S("имя параметра"),
          "desc": S("что это за вход — одной фразой"), "from": REF,
          "all_values": SL("ВСЕ значения из спеки, до объединения"),
          "values": SL("классы для матрицы; по умолчанию равны all_values"),
          "grouping": S("почему значения объединены — обязательно при объединении"),
          "special": SL("значения вне матрицы: таймаут, ответ не по схеме, "
                        "неизвестный статус"),
          "root": ROOT},
         ["model", "name", "desc", "from", "all_values"], sm.cmd_param_add,
         {"root": ".", "force": False}),

    tool("sm_param_rm", "Убрать параметр и всё, что на него ссылалось.",
         {"model": MODEL, "name": S("имя")}, ["model", "name"], sm.cmd_param_rm,
         {"root": "."}),

    tool("sm_exclude",
         "Упомянутое в спеке, но входом не являющееся — с причиной. Видно, что "
         "рассмотрено, а не забыто.",
         {"model": MODEL, "name": S("имя"), "reason": S("почему не влияет на исход")},
         ["model", "name", "reason"], sm.cmd_exclude, {"root": "."}),

    tool("sm_state_add",
         "Шаг 3. Состояние интерфейса: имя, что видит пользователь, ссылка на спеку. "
         "Условий нет — привязка к строкам делается после сборки матрицы. Опиши ВСЕ "
         "варианты UI: элемент показан и скрыт, загрузка, пусто, ошибка, "
         "заблокировано, свёрнуто, данные неполные.",
         {"model": MODEL, "name": S("название, например «Корзина грузится»"),
          "desc": S("что пользователь видит"), "evidence": REF, "root": ROOT},
         ["model", "name", "desc", "evidence"], sm.cmd_state_add, {"root": "."}),

    tool("sm_state_rm", "Убрать состояние вместе с его привязками.",
         {"model": MODEL, "name": S("название")}, ["model", "name"], sm.cmd_state_rm,
         {"root": "."}),

    tool("sm_rule_add",
         "Шаг 4. Правило свёртки матрицы. forbid вычёркивает невозможные комбинации, "
         "when+irrelevant схлопывает незначащие колонки в «∗». Основание берётся "
         "ТОЛЬКО из спеки: ссылка проверяется, выдуманная не пройдёт. Нет в спеке — "
         "спроси пользователя и попроси показать место.",
         {"model": MODEL, "id": S("короткий идентификатор"),
          "forbid": SL("запрет: пары параметр=значение,значение"),
          "when": SL("условие схлопывания: пары параметр=значение"),
          "irrelevant": SL("параметры, не влияющие на исход при этом условии"),
          "evidence": REF, "desc": S("правило человеческим языком"), "root": ROOT},
         ["model", "id", "evidence"], sm.cmd_rule_add, {"root": "."}),

    tool("sm_rule_rm", "Убрать правило.", {"model": MODEL, "id": S("идентификатор")},
         ["model", "id"], sm.cmd_rule_rm, {"root": "."}),

    tool("sm_build",
         "Шаг 5. Собрать матрицу: проверка ссылок, инварианты, свёртка. Пользователь "
         "НЕ ВИДИТ вывод тулов. Вывод делится надвое строкой «--- служебное»: ВЕРХ — "
         "готовая markdown-таблица, вставь её в чат как есть, ничего не переписывая "
         "и не сокращая. НИЗ — номера строк и воронка, они нужны тебе для sm_assign "
         "и наружу не идут.",
         {"model": MODEL, "root": ROOT}, ["model"], sm.cmd_build, {"root": "."}),

    tool("sm_assign",
         "Шаг 6. Привязать состояние к строкам матрицы по их номерам из служебной "
         "части последней сборки (r000, r001…). Строки, помеченные «?», — "
         "непокрытые случаи: по каждой либо назначь состояние, либо запрети "
         "комбинацию правилом, либо скажи пользователю, что это дыра в спеке. "
         "После привязок пересобери матрицу.",
         {"model": MODEL, "state": S("название состояния"),
          "rows": SL("номера строк: r000, r001")},
         ["model", "state", "rows"], sm.cmd_assign, {"root": "."}),

    tool("sm_rows",
         "Строки матрицы. С no_state — только те, которым состояние не назначено.",
         {"model": MODEL, "no_state": B("только строки без состояния"),
          "limit": {"type": "integer", "description": "сколько показать"}},
         ["model"], sm.cmd_rows, {"limit": 50, "no_state": False, "root": "."}),
]


def run_tool(t, args):
    """Зовёт функцию sm.py и возвращает её вывод. die() становится ошибкой тула.

    Пространство имён строится ПО СХЕМЕ тула: всё, что объявлено, существует —
    отсутствующее равно None. Иначе добавление аргумента в схему ломает вызов.
    """
    ns = {k: None for k in t["inputSchema"]["properties"]}
    ns.update(t["_defaults"])
    ns.update({k: v for k, v in args.items() if v is not None})
    if "from" in ns:
        ns["frm"] = ns.pop("from")
    for flag in ("force", "assumed", "env", "no_state"):
        ns[flag] = bool(ns.get(flag))
    ns.setdefault("frm", None)

    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            t["_fn"](SimpleNamespace(**ns))
    except SystemExit as e:
        if e.code:
            return (err.getvalue() or out.getvalue() or f"код выхода {e.code}"), True
    except Exception:
        return traceback.format_exc(limit=3), True
    text = out.getvalue() + err.getvalue()
    return text.rstrip() or "готово", False


def handle(msg):
    m, mid = msg.get("method"), msg.get("id")
    if m == "initialize":
        return {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                "serverInfo": {"name": "state-matrix", "version": VERSION}}
    if m == "tools/list":
        return {"tools": [{k: v for k, v in t.items() if not k.startswith("_")}
                          for t in TOOLS]}
    if m == "tools/call":
        p = msg.get("params") or {}
        t = next((x for x in TOOLS if x["name"] == p.get("name")), None)
        if not t:
            return {"content": [{"type": "text", "text": f"нет тула {p.get('name')}"}],
                    "isError": True}
        text, bad = run_tool(t, p.get("arguments") or {})
        return {"content": [{"type": "text", "text": text}], "isError": bad}
    if m == "ping":
        return {}
    return None if mid is None else {}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        try:
            result = handle(msg)
        except Exception:
            result = None
            if msg.get("id") is not None:
                sys.stdout.write(json.dumps({
                    "jsonrpc": "2.0", "id": msg["id"],
                    "error": {"code": -32603, "message": traceback.format_exc(limit=2)}}) + "\n")
                sys.stdout.flush()
                continue
        if msg.get("id") is not None and result is not None:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg["id"],
                                         "result": result}, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()

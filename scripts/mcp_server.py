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

TOOLS = [
    tool("sm_init",
         "Шаг 1. Завести модель по спецификации. После этого изучи спеку и ВСЕ "
         "ссылки из неё — соседние документы, схемы, задачи в трекере — прежде "
         "чем объявлять параметры.",
         {"model": MODEL, "system": S("имя системы"),
          "source": S("путь к спецификации")},
         ["model", "system", "source"], sm.cmd_init, {"force": False}),

    tool("sm_param_add",
         "Шаг 2. Объявить входной параметр — только имя, тип, описание и ссылку "
         "на место в спеке. Значения задаются позже, отдельно. Объяви СРАЗУ ВСЕ "
         "параметры, какие нашёл, и только потом переходи к значениям.",
         {"model": MODEL, "name": S("имя параметра"),
          "type": S("тип: string, number, enum, boolean, endpoint, array, date, file"),
          "desc": S("что это за вход и откуда берётся — одной фразой"),
          "from": S("ссылка: docs/spec.md:§3"),
          "env": B("не меняется в рантайме: делит матрицу на срезы, а не умножает её")},
         ["model", "name", "type", "desc", "from"], sm.cmd_param_add),

    tool("sm_exclude",
         "Упомянутое в спеке, но не являющееся входным параметром — с причиной. "
         "Так видно, что рассмотрено, а не забыто.",
         {"model": MODEL, "name": S("имя"), "reason": S("почему не влияет на исход")},
         ["model", "name", "reason"], sm.cmd_exclude),

    tool("sm_params",
         "Перечень объявленных параметров. Показывай его пользователю на воротах "
         "«все ли это параметры?» — до того, как задавать значения.",
         {"model": MODEL}, ["model"], sm.cmd_params),

    tool("sm_param_values",
         "Шаг 3. Значения одного параметра. Сначала all_values — ВСЕ значения из "
         "спеки, включая корнер-кейсы. Затем values — классы после объединения, и "
         "grouping — почему объединённые значения дают один исход. Откажет, если "
         "объединение не объяснено.",
         {"model": MODEL, "name": S("имя параметра"),
          "all_values": SL("ВСЕ значения из спеки, до объединения"),
          "values": SL("классы, идущие в матрицу; по умолчанию равны all_values"),
          "grouping": S("почему значения объединены — обязательно при объединении"),
          "special": SL("значения, проверяемые по одному вне матрицы: "
                        "пустое, предельное, неизвестное с бэкенда")},
         ["model", "name", "all_values"], sm.cmd_param_values),

    tool("sm_param_rm", "Убрать параметр и всё, что на него ссылалось.",
         {"model": MODEL, "name": S("имя")}, ["model", "name"], sm.cmd_param_rm),

    tool("sm_state_add",
         "Шаг 4. Именованное состояние интерфейса. Покрой ВСЕ варианты UI: элемент "
         "показан и скрыт, идёт загрузка, пусто, ошибка, заблокировано, свёрнуто, "
         "данные частичные. Порядок значим — частные случаи добавляй раньше общих. "
         "Требует ссылку на спеку: состояние без неё — выдумка.",
         {"model": MODEL, "name": S("название, например «Корзина грузится»"),
          "when": SL("условие: пары параметр=значение; пусто — запасное состояние"),
          "desc": S("что пользователь видит в этом состоянии"),
          "evidence": S("ссылка: docs/spec.md:§3")},
         ["model", "name", "desc", "evidence"], sm.cmd_state_add),

    tool("sm_state_rm", "Убрать состояние.", {"model": MODEL, "name": S("название")},
         ["model", "name"], sm.cmd_state_rm),

    tool("sm_states",
         "Список состояний по порядку. Показывай на воротах перед сборкой матрицы.",
         {"model": MODEL}, ["model"], sm.cmd_states),

    tool("sm_rule_add",
         "Шаг 5. Правило свёртки матрицы. forbid вычёркивает невозможные "
         "комбинации, when+irrelevant схлопывает незначащие колонки. Основание "
         "берётся ТОЛЬКО из спеки. Без ссылки вида spec.md:§3 правило становится "
         "assumed, в матрицу не идёт и требует ask — вопроса пользователю.",
         {"model": MODEL, "id": S("короткий идентификатор"),
          "forbid": SL("запрет: пары параметр=значение,значение"),
          "when": SL("условие схлопывания: пары параметр=значение"),
          "irrelevant": SL("параметры, не влияющие на исход при этом условии"),
          "evidence": S("ссылка на спеку"),
          "desc": S("правило человеческим языком"),
          "ask": S("вопрос пользователю, если доказательства в спеке нет"),
          "assumed": B("принудительно понизить статус")},
         ["model", "id", "evidence"], sm.cmd_rule_add),

    tool("sm_rule_rm", "Убрать правило.", {"model": MODEL, "id": S("идентификатор")},
         ["model", "id"], sm.cmd_rule_rm),

    tool("sm_transition_add",
         "Переход между состояниями — нужен, если спека описывает последовательность. "
         "Без переходов достижимость не считается.",
         {"model": MODEL, "event": S("имя события"),
          "when": SL("условие применимости"),
          "set": SL("что меняется: пары параметр=значение, допустимо !параметр"),
          "evidence": S("ссылка на спеку")},
         ["model", "event", "set", "evidence"], sm.cmd_transition_add),

    tool("sm_show", "Вся модель целиком: параметры, правила, состояния, переходы.",
         {"model": MODEL}, ["model"], sm.cmd_show),

    tool("sm_build",
         "Шаг 6. Собрать матрицу: проверка ссылок, инварианты, свёртка, "
         "достижимость. Возвращает сводку, состояния с числом строк, саму матрицу "
         "и находки — покажи это пользователю целиком. Откажет, если у параметров "
         "нет значений или не описано ни одного состояния.",
         {"model": MODEL, "root": S("корень репозитория для проверки ссылок"),
          "env": {"type": "integer", "description": "номер среза окружения"}},
         ["model"], sm.cmd_build, {"root": ".", "env": 0}),

    tool("sm_rows",
         "Строки матрицы. С no_state — только те, которым не досталось состояния: "
         "по каждой реши, описать новое состояние или запретить комбинацию.",
         {"result": S("путь к .states/runs/<Имя>.json"),
          "no_state": B("только строки без состояния"),
          "status": S("фильтр: described, undefined, unreachable, contradictory"),
          "limit": {"type": "integer", "description": "сколько показать"}},
         ["result"], sm.cmd_rows, {"env": 0, "limit": 50, "no_state": False, "status": None}),

    tool("sm_result", "Показать уже собранную матрицу, в том числе другой срез окружения.",
         {"result": S("путь к .states/runs/<Имя>.json"),
          "env": {"type": "integer", "description": "номер среза"}},
         ["result"], sm.cmd_result, {"env": 0}),

    tool("sm_answer",
         "Ответ пользователя на неподтверждённое правило или на строку матрицы.",
         {"model": MODEL, "id": S("идентификатор правила или ключ строки"),
          "value": S("proven, rejected, described или contradictory"),
          "section": {"type": "string", "enum": ["constraints", "outcomes"]}},
         ["model", "id", "value"], sm.cmd_answer, {"section": "constraints"}),
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

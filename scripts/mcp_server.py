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
    tool("sm_init", "Завести пустую модель. Первый шаг всегда.",
         {"model": MODEL, "system": S("имя системы"),
          "source": S("путь к спецификации"),
          },
         ["model", "system", "source"], sm.cmd_init, {"force": False}),

    tool("sm_extract",
         "Кандидаты в параметры из файла с кодом (React/TS). Каждый обязан попасть "
         "либо в параметры, либо в sm_exclude с причиной.",
         {"target": S("путь к файлу")}, ["target"], None),

    tool("sm_catalog",
         "ОБЯЗАТЕЛЬНЫЙ шаг перед добавлением параметра. Ищет семантику в корзине "
         "и печатает её обязательные вопросы. Без этого вызова sm_param_add откажет.",
         {"model": MODEL, "name": S("имя параметра"),
          "type": S("тип: string, number, enum, boolean, endpoint, array, date, file")},
         ["model", "name", "type"], sm.cmd_catalog),

    tool("sm_catalog_list",
         "Список типов параметров: идентификатор, название, описание. Вопросы не "
         "показывает — их даёт sm_catalog_get по выбранному типу.",
         {"type": S("необязательный фильтр по типу значения")}, [], sm.cmd_catalog_list,
         {"model": ".", "type": None}),

    tool("sm_catalog_get",
         "Карточка типа: все его вопросы, значения по умолчанию, спецзначения "
         "и типичные имена. У каждого вопроса есть варианты ответа — предлагай их "
         "пользователю, а не спрашивай открытым текстом.",
         {"model": MODEL, "id": S("идентификатор типа, например http_endpoint")},
         ["model", "id"], sm.cmd_catalog_get),

    tool("sm_catalog_edit",
         "Дополнить существующий тип. Вызывай это КАЖДЫЙ РАЗ, когда пользователь "
         "задал вопрос, которого не было в типе, или поправил тебя по существу: "
         "тогда в следующий раз вопрос задастся сам. Правка ложится в проектную "
         "корзину и переживает обновление плагина.",
         {"model": MODEL, "id": S("идентификатор типа"),
          "add_questions": SL("новые вопросы: id=текст вопроса?|вариант|вариант"),
          "add_names": SL("имена параметров, по которым этот тип должен находиться"),
          "add_values": SL("новые классы значений"),
          "add_special": SL("новые спецзначения"),
          "desc": S("уточнённое описание типа")},
         ["model", "id"], sm.cmd_catalog_edit),

    tool("sm_catalog_new",
         "Завести новый тип параметра, когда ни один существующий не подошёл. "
         "Нужны название и описание — по ним тип выбирают из списка. "
         "Вопросы обязаны заканчиваться знаком вопроса.",
         {"model": MODEL, "id": S("идентификатор, например order_status"),
          "title": S("название по-русски, например «Статус заказа»"),
          "desc": S("что это за вид параметра и какие у него ловушки"),
          "type": S("тип параметров этой семантики"),
          "names": SL("типичные имена параметров"),
          "questions": SL("вопросы: id=текст вопроса?|вариант|вариант"),
          "values": SL("классы значений"), "special": SL("спецзначения вне матрицы")},
         ["model", "id", "title", "desc", "type", "questions"], sm.cmd_catalog_new),

    tool("sm_param_add",
         "Добавить параметр. Откажет, если для этого имени не вызывали sm_catalog "
         "или не отвечены все вопросы семантики. Ответ ищи в типе, схеме, спеке; "
         "если нигде нет — спроси пользователя, а не пиши «неизвестно».",
         {"model": MODEL, "name": S("имя"), "type": S("тип"),
          "all_values": SL("ВСЕ возможные значения параметра из спеки, до объединения. "
                           "Перечисли их прежде, чем сворачивать в классы."),
          "values": SL("классы значений, идущие в матрицу"),
          "grouping": S("почему значения объединены в классы — обязательно, "
                        "если классов меньше, чем значений"),
          "special": SL("спецзначения: проверяются по одному, вне произведения"),
          "from": S("источник: file.ts:27 или docs/spec.md:§3"),
          "desc": S("что это и почему значения такие"),
          "answers": SL("ответы на вопросы типа в виде id=ответ. Отвечай только на то, "
                        "что нашёл в источниках; остальное само пометится «не выяснено» "
                        "и уйдёт в отчёт — переспрашивать пользователя не обязательно"),
          "catalog": S("id семантики, если по имени не определилась"),
          "env": B("параметр не меняется в рантайме: делит матрицу на срезы")},
         ["model", "name", "type", "all_values", "values", "from"],
         sm.cmd_param_add),

    tool("sm_param_rm", "Убрать параметр и все ссылающиеся на него правила.",
         {"model": MODEL, "name": S("имя")}, ["model", "name"], sm.cmd_param_rm),

    tool("sm_exclude", "Учесть кандидата как не-параметр с причиной.",
         {"model": MODEL, "name": S("имя"), "reason": S("почему не влияет на исход")},
         ["model", "name", "reason"], sm.cmd_exclude),

    tool("sm_rule_add",
         "Правило свёртки. forbid вычёркивает невозможные комбинации, "
         "when+irrelevant схлопывает незначащие колонки. Без ссылки file:line "
         "или file.md:§N правило становится assumed, не применяется и требует ask.",
         {"model": MODEL, "id": S("короткий идентификатор"),
          "forbid": SL("запрет: пары параметр=значение,значение"),
          "when": SL("условие схлопывания: пары параметр=значение"),
          "irrelevant": SL("параметры, не влияющие на исход при этом условии"),
          "evidence": S("ссылка на спеку или код"),
          "desc": S("правило человеческим языком"),
          "ask": S("вопрос человеку, если доказательства нет"),
          "assumed": B("принудительно понизить до assumed")},
         ["model", "id", "evidence"], sm.cmd_rule_add),

    tool("sm_rule_rm", "Убрать правило.", {"model": MODEL, "id": S("идентификатор")},
         ["model", "id"], sm.cmd_rule_rm),

    tool("sm_state_add",
         "Именованное состояние системы из спеки. Порядок значим: побеждает первое "
         "подходящее, поэтому частные случаи добавляй раньше общих.",
         {"model": MODEL, "name": S("название, например «Пустая корзина»"),
          "when": SL("условие: пары параметр=значение"),
          "desc": S("что видит пользователь"),
          "evidence": S("ссылка на спеку")},
         ["model", "name", "evidence"], sm.cmd_state_add),

    tool("sm_state_rm", "Убрать состояние.", {"model": MODEL, "name": S("название")},
         ["model", "name"], sm.cmd_state_rm),

    tool("sm_transition_add",
         "Переход между состояниями. Без переходов достижимость не считается.",
         {"model": MODEL, "event": S("имя события"),
          "when": SL("условие применимости"),
          "set": SL("что меняется: пары параметр=значение, допустимо !параметр"),
          "evidence": S("ссылка")},
         ["model", "event", "set", "evidence"], sm.cmd_transition_add),

    tool("sm_rows",
         "Строки матрицы для разбора. С no_state — только те, которым не назначено "
         "состояние: это и есть непокрытые случаи.",
         {"result": S("путь к .states/runs/<Имя>.json"),
          "no_state": B("только строки без состояния"),
          "status": S("фильтр: described, undefined, unreachable, contradictory"),
          "limit": {"type": "integer", "description": "сколько показать"}},
         ["result"], sm.cmd_rows, {"env": 0, "limit": 50, "no_state": False, "status": None}),

    tool("sm_answer", "Ответ человека на неподтверждённое правило или строку.",
         {"model": MODEL, "id": S("идентификатор правила или ключ строки"),
          "value": S("proven, rejected, described или contradictory"),
          "section": {"type": "string", "enum": ["constraints", "outcomes"]}},
         ["model", "id", "value"], sm.cmd_answer, {"section": "constraints"}),

    tool("sm_show", "Модель человеческим текстом: параметры, правила, состояния.",
         {"model": MODEL}, ["model"], sm.cmd_show),

    tool("sm_build",
         "Собрать: проверка ссылок, инварианты, матрица, отчёт. Останавливается "
         "на первом непройденном шаге. Печатает отчёт — его надо отдать целиком.",
         {"model": MODEL, "root": S("корень репозитория для проверки ссылок")},
         ["model"], sm.cmd_build, {"root": "."}),
]


def run_tool(t, args):
    """Вызывает функцию sm.py и возвращает её вывод. die() превращается в ошибку."""
    if t["name"] == "sm_extract":
        cands, branches, nlines = extract.scan(args["target"])
        lines = [f"{args['target']}: {nlines} строк, ветвлений {branches}",
                 f"кандидатов {len(cands)} — каждый в параметры или в sm_exclude:"]
        for c in cands:
            lines.append(f"  {c['kind']:9} {c['name']:16} :{c['line']:<4} {c['text']}")
        return "\n".join(lines), False

    ns = dict(t["_defaults"])
    ns.update({k: v for k, v in args.items() if v is not None})
    if "answers" in ns:
        ns["answer"] = ns.pop("answers")
    if "from" in ns:
        ns["frm"] = ns.pop("from")
    for k in ("forbid", "when", "irrelevant", "set", "names", "questions",
              "values", "special", "answer", "all_values", "add_questions", "add_names",
              "add_values", "add_special", "title", "id"):
        ns.setdefault(k, None)
    ns.setdefault("force", False)
    ns.setdefault("assumed", False)
    ns.setdefault("env", False)
    ns.setdefault("desc", None)
    ns.setdefault("ask", None)
    ns.setdefault("catalog", None)
    ns.setdefault("grouping", None)
    ns.setdefault("evidence", None)

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

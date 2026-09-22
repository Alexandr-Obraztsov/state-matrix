# state-matrix

Плагин Claude Code. Разбирает спецификацию или код на входные параметры, их
значения и состояния системы, сворачивает матрицу по правилам из спеки и
показывает комбинации, о которых спека молчит.

Не генератор тестов: он ищет дыры, противоречия и недостижимые состояния.

## Установка

```bash
/plugin marketplace add https://github.com/<user>/state-matrix
/plugin install state-matrix
```

Без доступа к GitHub — с локального пути:

```bash
/plugin marketplace add /путь/к/state-matrix
/plugin install state-matrix
```

Зависимостей нет: только `python3`. Ничего устанавливать не нужно.

## Как пользоваться

Дай агенту спеку и попроси построить матрицу состояний — скилл подтянется сам.
Либо явно: `/states docs/checkout.md`.

Агент проведёт через четыре этапа, спрашивая одобрение на каждом:

1. **Параметры** — что вообще является входом и какие значения принимает
2. **Состояния** — именованные состояния системы из спеки
3. **Матрица и правила** — свёртка по зависимостям, подтверждённым спекой
4. **Исходы и отчёт** — что не покрыто и что нужно дозаполнить

## Вручную

```bash
S=~/.claude/plugins/.../state-matrix/scripts

python3 $S/sm.py init .states/models/Checkout.states.json \
        --system Checkout --source docs/checkout.md --mode spec
python3 $S/sm.py catalog-list
python3 $S/sm.py catalog .states/models/Checkout.states.json amount --type number
python3 $S/sm.py param add .states/models/Checkout.states.json --name amount ...
python3 $S/sm.py build .states/models/Checkout.states.json --root .
```

`python3 -m unittest discover -s tests` — тесты плагина.

## Что делает строгим

- `param add` отказывает, пока не запрошена корзина и не отвечены её вопросы
- `rule add` без ссылки `file:line` понижает правило до `assumed`: оно не
  применяется к матрице и требует вопроса человеку
- `verify.py` проверяет каждую ссылку: файл, строка, упоминание параметра
- `validate.py` ловит параметр, добавленный в обход тулов
- потолок 100 строк: превышение печатает разбор, а не «слишком много»

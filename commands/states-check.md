---
description: Проверить все модели состояний в проекте и сам плагин
---

Проверь состояние матриц в этом проекте:

1. Прогони тесты плагина: `python3 ${CLAUDE_PLUGIN_ROOT}/tests` через `python3 -m unittest discover`.
2. Для каждой модели в `.states/models/*.states.json` выполни
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/verify.py <модель> --root .` и
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/validate.py <модель>`.
3. Сообщи одной таблицей: модель, число параметров, число строк, ошибки.

Ничего не чини без спроса — только покажи, что сломано.

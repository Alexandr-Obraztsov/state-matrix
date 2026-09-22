# state-matrix

Плагин Claude Code. Поднимает все состояния системы, считает достижимость
и показывает комбинации, о которых код или спека молчат.

```bash
python3 scripts/validate.py examples/checkout-widget.states.yaml
python3 scripts/engine.py  examples/checkout-widget.states.yaml -o .states/runs/checkout-widget.json
python3 scripts/serve.py   --data .states/runs/checkout-widget.json
python3 -m unittest discover -s tests
```

Отчёт — `http://localhost:4177`. Ответы из отчёта пишутся в `.states/answers.yaml`
и подхватываются следующим прогоном (`-a`).

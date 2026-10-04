# Отчёты по `SCHEDULER` — НОЦ, 5-й сезон

Отчёты по неделям вокруг модуля [`SCHEDULER.py`](https://github.com/sherokiddo/project_py_scheduler/blob/dev/PyScheduler/SCHEDULER.py) из репозитория [`sherokiddo/project_py_scheduler`](https://github.com/sherokiddo/project_py_scheduler/tree/dev) (ветка `dev`).

| Неделя | Отчёт | Содержание |
|---|---|---|
| 01 | [`docs/week_01_report.md`](docs/week_01_report.md) | Структура и назначение `SCHEDULER.py`: модели планирования (Round Robin, Best CQI, Proportional Fair, частотные FD-варианты), CQI, буфер, TTI и состояние между вызовами, PDCCH и CCE, AMC, метрики |
| 02 | [`docs/week_02_report.md`](docs/week_02_report.md) | Полный scheduling cycle: карта всего кода файла, схема вызовов `schedule()` с номерами строк, этапы одного TTI (входы, выходы, побочные эффекты), сценарий «3 UE, BestCQI, 10 МГц, TTI 5» из живого прогона, сверка с 3GPP |
| 03 | [`docs/week_03_report.md`](docs/week_03_report.md) | Сравнение с srsRAN (две кодовые базы: 4G LTE и Project NR) прямо по коду — фрагменты вставлены в текст один против другого: пайплайны TTI/слота, аллокаторы данных RBG/PRB и контроля CCE/PDCCH, частотно-селективный выбор по subband CQI и формирование маски RBG, совместное распределение UE × RBG и венгерский метод, метрика Proportional Fair, LCP, HARQ, AMC и TBS, границы модулей; итоги — зазоры и что перенимать |

Дополнительные материалы:

- [`docs/discussion_allocation_order.md`](docs/discussion_allocation_order.md) — записка к обсуждению: порядок аллокации DL «PDCCH → PDSCH» против «PDSCH → PDCCH» — что говорит 3GPP, как сделано в srsRAN 4G (data-first + атомарный commit) и srsRAN Project (control-first + откаты), вопросы к решению.
- [`interactive/scheduler_playground.html`](interactive/scheduler_playground.html) — интерактивная модель планировщика на основе кода `SCHEDULER.py`: полностью автономный файл.
- [`scripts/scenario_tti5.py`](scripts/scenario_tti5.py) — скрипт стенда из отчёта Week 02 §6: собирает ресурсы, BS и трёх UE, вызывает `schedule(5, users)` и печатает состояние до/после, verbose-лог и статистику.

## Оформление

В отчётах используются локальные SVG-материалы (`docs/assets/`, с анимациями), Mermaid-блоки, GitHub-алерты (`> [!NOTE]` и т.п.), нативный LaTeX (`$…$`) и сноски (`[^…]`) — всё это Obsidian и GitHub рендерят непосредственно из Markdown без плагинов и настроек. Материалы недели 03 лежат там же: уникальные имена файлов (`hero_srsran.svg`, `arch_4g_ru.svg`, …), разделители — в `docs/assets/separators_w3/`, чтобы не пересекаться с ассетами недель 01–02. Все схемы week 03 нарисованы для отчёта, изображений из интернета в нём нет.

Каждое утверждение снабжено ссылкой: номер строки нашего кода (кликабельный deep-link на dev-ветку), номер строки srsRAN (ветки `master`/`main`), спецификация 3GPP или документация модуля из `PyScheduler/Documentation/`.
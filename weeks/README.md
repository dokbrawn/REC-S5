# SCHEDULER.py — планировщик радиоресурсов (LTE DL)

> Ответственный: Тимур (Scheduler)  
> Состояние: описан  
> Проверено по коду: `ae9db40` | Обновлено: `2026-10-10`

Источник: [`PyScheduler/SCHEDULER.py`](https://github.com/sherokiddo/project_py_scheduler/blob/ae9db40ecfd27787b4cdeba79bcb6eafabd7d44b/PyScheduler/SCHEDULER.py), версия модуля v2.1.0, 2694 строки. Ссылки даны в формате `файл::символ (:строка)`; номера строк действительны для коммита `ae9db40`. Все приведённые числа и поведение проверены фактическими запусками на этом коммите. Авторская документация модуля: [`Documentation/doc_scheduler_v2.1.0.md`](https://github.com/sherokiddo/project_py_scheduler/blob/ae9db40ecfd27787b4cdeba79bcb6eafabd7d44b/PyScheduler/Documentation/doc_scheduler_v2.1.0.md).

## 1. Назначение

Модуль решает задачу MAC-планировщика downlink: один раз в TTI (1 мс) определяет, какие пользователи (UE) получат радиоресурс и какие именно группы ресурсных блоков (RBG) им достанутся — с учётом качества канала (CQI), заполненности буферов базовой станции и бюджета управляющего канала PDCCH (CCE). Реализованы шесть алгоритмов планирования (BestCQI, ProportionalFair, RoundRobin и три частотно-селективных FD-варианта), выбираемых через фабрику. Кроме принятия решения модуль пока сам исполняет его: извлекает пакеты из буфера BS и обновляет статистику throughput UE; расслоение запланировано самим кодом (roadmap-комментарий :2676–2694, см. [features.md](docs/features.md) OPT-SCH-007).

## 2. Границы ответственности

**Делает:**
- Полный pipeline одного TTI (этапы 0–8, `SCHEDULER.py::SchedulerInterface.schedule` :340): обновление карты CQI → отбор допущенных UE → скользящее окно → приоритеты → оценка потребности PDSCH → выделение CCE → распределение RBG → извлечение из буфера → статистика и результат.
- Шесть алгоритмов через фабрику `SchedulerInterface.create()` (:233): `'BestCQI'`, `'ProportionalFair'`, `'RoundRobin'`, `'FD_BCQI'`, `'FD_FGS'`, `'FD_PF'`.
- Учёт бюджета CCE (`PDCCHManager` :1232) и перевод CQI в оценку ёмкости RB (`AdaptiveModulationAndCoding` :1673).
- Хранение CQI между отчётами (`CQIMap` :189), формирование грантов извлечения (`SchedulingGrant` :115), мультиплексирование логических каналов (`_logical_channel_multiplexing` :805, режимы Simple/Layered).
- Накопление статистики TTI: `get_stats()` (:432), `amc.get_stats()` (:1725), `pdcch_manager.get_stats()` (:1630).

**Не делает (относится к соседним модулям):**
- Не измеряет канал: `cqi`/`sbb_cqi` приходят готовыми из `UE_MODULE.py::GET_USERS_FOR_SCHEDULER` (:901), где формируются `UE_MODULE.py::SINR_TO_CQI` (:693).
- Не генерирует трафик и не владеет буферами: их хранит `BS_MODULE` (`IBufferManager` :260, реализации `SimpleBufferManager` :368 и `LayeredBufferManager` :1113); планировщик читает статус и извлекает по грантам.
- Не владеет ресурсной сеткой: занятие RB выполняет `RES_GRID.py::ALLOCATE_RBG` (:430, атомарно с откатом `RELEASE_RBG` :440).
- Не реализует HARQ: `harq_manager = None` (:335), `_get_harq_retransmissions` (:1201) — заготовка; поля гранта `ndi`/`rv`/`harq_process_id` не используются.
- Не реализует QoS/LCP-приоритеты: в Layered-режиме TB делится поровну между активными логическими каналами (комментарий в коде называет стратегию несправедливой, :855–857); QoS-планировщики находятся в открытом PR #39 (не слит).

## 3. Входы, выходы и зависимости

| Вход | Откуда | Формат/смысл |
|---|---|---|
| `tti: int` | `SIMULATION_MANAGER.py::run_tti` (:1491, вызов :1535) | номер текущего TTI (1 мс) |
| `users: List[Dict]` | `UE_MODULE.py::GET_USERS_FOR_SCHEDULER` (:901–919) | срез состояния на начало TTI, ровно 4 поля: `UE_ID`, `cqi` (WB 1–15), `sbb_cqi` (per-RBG список; **ключ с опечаткой — устоявшийся контракт обеих сторон**, audit DOC-SCH-001), `ue` (живая ссылка на объект UE) |
| размеры буферов | `BS_MODULE.py::IBufferManager.ue_has_buffer/get_buffer_status` (:318/:280) | читаются напрямую на этапе 1, дописываются в `users[i]['bs_buffer_size']` |
| `lte_grid`, `bs` | конструктор (:288); конфигурация — `SIMULATION_MANAGER.py::SchedulerConfig` (:871) | `GET_RBG_SIZE` (:421), `GET_RBG_INDICES` (:424), `ALLOCATE_RBG` (:430), `GENERATE_BITMAP` (:567); `bs.buffer_manager`, `bs.use_simple_buffer` (:1439) |

| Выход | Куда | Формат/смысл |
|---|---|---|
| возврат `schedule()` | `SIMULATION_MANAGER` | `{allocation: {UE_ID: [freq_idx]}, statistics: {}, bitmap: {UE_ID: [17 бит]}, pdcch_stats}`; **в главном цикле результат отбрасывается**: `_ = self.run_tti(...)` (SIMULATION_MANAGER.py:1289), audit OPT-SCH-005 |
| статистика | `StatsManager` (SIMULATION_MANAGER.py:108, `collect` :156) | фактический канал данных наружу: три `get_stats()` читают кэш `_last_*`, заполняемый на этапе 7.5 |
| извлечение пакетов | `BS_MODULE::get_packets(grants)` (:295, Layered :1196) | побочный эффект этапа 7: буфер BS физически уменьшается |
| throughput UE | `UE_MODULE.py::UPD_DL_THROUGHPUT_BPS` (:629) | побочный эффект этапа 7: `current_dl_throughput` и EWMA `average_throughput` (α=0.002 хардкод, :644; TODO «вывести в управление», issue #31) — знаменатель PF следующих TTI |
| занятые RB | `RES_GRID::ALLOCATE_RBG` (:430) | побочный эффект этапа 6: RBG заняты в обоих слотах подкадра до переиспользования (кадр = 10 подкадров) |

Зависимости: `GLOBALS` (`BITS_PER_BYTE` :140, `bytes_to_bits` :201), `time`, `dataclasses`, `typing`; runtime — RES_GRID, BS_MODULE, UE_MODULE, SIMULATION_MANAGER. Импорт `BaseStation` (:111) не используется (audit OPT-SCH-006).

## 4. Как проверить работу

**Минимальный сценарий** (проверен на `ae9db40`; сохранить как `PyScheduler/_check.py` и запустить `python3 _check.py` из каталога `PyScheduler/`, нужен numpy):

```python
import GLOBALS
from RES_GRID import RES_GRID_LTE
from BS_MODULE import BaseStation
from UE_MODULE import UserEquipment
from TRAFFIC_MODEL import Packet
from SCHEDULER import SchedulerInterface

GLOBALS.CURRENT_TIME = 5
bs   = BaseStation(bandwidth=10, use_simple_buffer=True)
grid = RES_GRID_LTE(bandwidth=10, num_frames=2)
sched = SchedulerInterface.create('BestCQI', grid, bs)

ues = []
for ueid, cqi, nbytes in ((1, 13, 1000), (2, 7, 5000), (3, 15, 300)):
    ue = UserEquipment(UE_ID=ueid, x=100.0 * ueid, y=0.0)
    ue.cqi, ue.cqi_subband = cqi, []
    bs.buffer_manager.create_ue_buffer(ueid, bs.per_ue_max)
    bs.buffer_manager.add_packet(ueid, Packet(size=nbytes, ue_id=ueid, creation_time=0))
    ues.append(ue)

users = [{"UE_ID": u.UE_ID, "cqi": u.cqi, "sbb_cqi": u.cqi_subband, "ue": u} for u in ues]
res = sched.schedule(5, users)
print(res['allocation'])
```

Ожидаемый результат (фактический прогон): `allocation = {1: [6..17], 2: [], 3: [0..5]}` — 18 RB из 50 (PRB util 36%); `pdcch_ue_cce_allocations = {3: 1, 1: 1}` (2/25 CCE); UE2 отсечён оценкой PDSCH (порог 95%) и не тратит CCE; извлечено 8004/2404 бита у UE1/UE3; `average_throughput` = 16008/4808 бит/с (EWMA α=0.002).

**Тесты:** `PyScheduler/tests/scheduler_tests/` — 27 тестовых функций (`test_scheduler_common.py`, `test_fd_best_cqi.py`, `test_fd_proportional_fair.py`, `test_fd_round_robin.py`) и бенчмарк `FD_benchmark.py`. Запуск — из каталога `PyScheduler/`: `python3 -m pytest tests/scheduler_tests/ -q` (из корня репозитория импорт `SCHEDULER` не разрешается: тесты добавляют в `sys.path` только каталог `tests/`, а модули проекта разрешаются через cwd). **Внимание: на `dev` набор сейчас неработоспособен** — отсутствует импортируемый всеми файлами модуль `log_utils` (есть только в ветках `multithread`/`feature/AMC`). Проверено на свежем чистом клоне: (A) как есть — 4 ошибки сборки независимо от каталога запуска; (B) после возврата `log_utils.py` — 15 failed / 12 passed (14 — устаревшее имя `'FD_RR'`, 1 — содержательный инвариант FD_PF); (C) после замены `'FD_RR'`→`'FD_FGS'` — 26 passed / 1 failed. Подробности: [audit.md](docs/audit.md) BUG-SCH-008; восстановление набора — запрос к автору модуля в [features.md](docs/features.md) §2 (в объём работ по модулю не входит).

## 5. Основные компоненты

| Файл / класс / функция | Назначение | Где используется |
|---|---|---|
| `SCHEDULER.py::SchedulingGrant` (:115) | dataclass гранта извлечения: `ue_id`, `num_bytes`, `lcid`, `ndi`, `harq_process_id`, `rv`; валидация `num_bytes ≥ 0`, `rv ∈ [0..3]` (:137); `to_dict()` (:158) | создаётся в `_logical_channel_multiplexing` (:805), потребляется `BS_MODULE::get_packets` (issue #27 — полная интеграция) |
| `SCHEDULER.py::CQIMap` (:189) | хранилище CQI на UE: `wb_cqi`, `sb_cqi` (per-RBG, длина = num_rbg), метки времени обновлений | пишет `_refresh_cqi` (:498), читают `_get_wb_cqi` (:1034) / `_get_sb_cqi` (:1054) |
| `SCHEDULER.py::SchedulerInterface` (:214) | оркестратор этапов 0–8 + фабрика: `create` (:233), `available_algorithms` (:273), `schedule` (:340), `get_stats` (:432), методы этапов (:498–1138), абстрактные `_calculate_priorities` (:1142) и `_allocate_pdsch` (:1167), HARQ-заготовка (:1201) | `SIMULATION_MANAGER` (создание :1196, вызов :1535) |
| `SCHEDULER.py::PDCCHManager` (:1232) | бюджет CCE: `_validate_parameters` (:1277), таблица `_calculate_total_cce` (:1317), `get_aggregation_level` (:1386), `check_cce_availability` (:1435), `allocate_cce` (:1466), `reset_tti` (:1515), `release_cce` — **заглушка** (:1538), `get_stats` (:1630) | этап 5 `_allocate_pdcch` (:763) |
| `SCHEDULER.py::AdaptiveModulationAndCoding` (:1673) | `CQI_TO_MCS` (:1680), `GET_BITS_PER_RB` (:1700) — единственная точка перевода CQI в биты (этапы 4.5, 6, 7, статистика); `get_stats` (:1725) читает кэш `_last_*` планировщика | весь модуль; TODO замены на TBS-таблицы :1718 (issue #30) |
| `BestCQIScheduler` (:1847) | priority = WB CQI (:1878); жадное TD-распределение (:1901) | фабрика `'BestCQI'` |
| `RoundRobinScheduler` (:1955) | ротация очереди от `rr_ue_offset` (:1985); по 1 RBG каждому по кругу (:2010); оценка PDSCH — pass-through (:1966) | фабрика `'RoundRobin'` |
| `ProportionalFairScheduler` (:2073) | priority = `instant_rate / (average_throughput/1000)` (:2088, fallback при нулевой истории :2104); жадное TD (:2130) | фабрика `'ProportionalFair'` |
| `FDxBestCQIScheduler` (:2185) | на каждом RBG побеждает max SB CQI с fallback на WB (:2239, выбор :2274) | фабрика `'FD_BCQI'` |
| `FDxFairGreedyScheduler` (:2309) | RR-ротация в TD (:2364) + per-RBG выбор по SB CQI с ограничением «один UE — один RBG за раунд» (`served_in_round` :2418–2475); до ревью PR #26 класс носил имя FD_RR | фабрика `'FD_FGS'` |
| `FDxProportionalFairScheduler` (:2494) | WB PF задаёт порядок выдачи CCE (:2558); на каждом RBG побеждает max PF-метрики по SB CQI (:2601, цикл :2615) | фабрика `'FD_PF'` |
| roadmap-комментарий (:2676–2694) | планы из самого кода: BufferManager, DCI + AllocationTracker, каноничный output, QoS, tie-break, исследование венгерского/жадного распределения RBG, оценка средней пропускной способности PF, защита голодающих UE | основа [features.md](docs/features.md) |

Матрица переопределений (различия алгоритмов локальны — базовый класс реализует весь цикл):

| Планировщик | `_calculate_priorities` | `_apply_pdsch_estimation` | `_allocate_pdsch` | доп. состояние |
|---|---|---|---|---|
| BestCQI (:1847) | WB CQI (:1878) | базовый, порог 95% (:706) | жадный TD (:1901) | — |
| RoundRobin (:1955) | ротация очереди (:1985) | pass-through (:1966) | 1 RBG по кругу (:2010) | `rr_rbg_offset`, `rr_ue_offset` |
| ProportionalFair (:2073) | r/R (:2088) | базовый (95%) | жадный TD (:2130) | — |
| FD_BCQI (:2185) | WB CQI (:2220) | pass-through (:2213) | per-RBG max SB CQI (:2239) | — |
| FD_FGS (:2309) | RR-ротация (:2364) | pass-through (:2347) | per-RBG SB CQI + `served_in_round` (:2393) | `rr_*_offset` |
| FD_PF (:2494) | WB PF (:2558) | pass-through (:2541) | per-RBG PF по SB CQI (:2601) | — |

Ключевые константы (дефолты `__init__` :288 и пороговые значения): `pcfich=2`; `max_dl_ue_tti=None` (без лимита); `window_size=100`, `enable_window=True`; `wb/sb_cqi_upd_interval=1` (каждый TTI); порог оценки PDSCH 95% `rb_per_slot` (:727); aggregation level: CQI 13–15→1, 10–12→2, 7–9→4, 1–6→8 CCE (:1386); бюджет CCE при 10 МГц: PCFICH 1/2/3 → 8/25/41 (:1317); RBG при 10 МГц: 3 RB → 17 RBG (`RES_GRID.py::RBG_SIZE_TABLE` :293); bits/RB (PCFICH=2, 1 порт): CQI 15→798, 13→755, 7→326 (:1700).

## 6. Один типичный сценарий

Вызов `schedule(tti=5, users)` из `SIMULATION_MANAGER.run_tti()` (BestCQI, 10 МГц, сценарий раздела 4 — все числа из фактического прогона на `ae9db40`):

1. **Этап 0** `_refresh_cqi` (:498) — WB CQI 13/7/15 записаны в `cqi_map` (SB-списки пусты — TD-сценарий).
2. **Этап 1** `_filter_eligible_ues` (:553) — все трое допущены (буферы существуют и непустые, CQI валидны); побочно: **всем** users сброшен `ue.current_dl_throughput = 0`, дописан `bs_buffer_size` = 1000/5000/300.
3. **Этапы 2–4** — окно: `_ue_queue` = [1,2,3] с ротацией (:604/:647); приоритеты = WB CQI; `priority_list` = [3, 1, 2] (:678).
4. **Этап 4.5** `_apply_pdsch_estimation` (:706) — потребность: UE3 = 2400//798 = 3 RB, UE1 = 8000//755 = 10 RB, UE2 = min(40000//326, 50) = 50 RB; с UE2 сумма 63 ≥ порога 47.5 → **UE2 отсечён** («13/50 RB = 26.0%, 1 UE excluded»), CCE не тратит.
5. **Этап 5** `_allocate_pdcch` (:763) — `reset_tti()`, CQI 15/13 ∈ [13–15] → по 1 CCE в порядке priority-списка: `{3: 1, 1: 1}`, занято 2 из 25 (8%).
6. **Этап 6** `_allocate_pdsch` (:1901) — жадно: RBG 0–1 → UE3 (остаток буфера исчерпан), RBG 2–5 → UE1; `allocation = {1: [6..17], 2: [], 3: [0..5]}`, 18 из 50 RB; каждый RBG занят атомарно через `ALLOCATE_RBG` (оба слота, откат при неудаче).
7. **Этап 7** `_process_buffers` (:874) — вместимость по WB CQI (UE1: 12·755 = 9060 бит → 1132 B; UE3: 6·798 = 4788 бит → 598 B) → гранты `SchedulingGrant` → `get_packets` извлекает 1000 B и 300 B → `UPD_DL_THROUGHPUT_BPS`: 8004 и 2404 бита (включая остаток `max_bits mod 8`, помеченный в коде «временный костыль» :922), EWMA-среднее 16008/4808 бит/с.
8. **Этапы 7.5–8** — счётчики в `_last_*` (:1074/:1124); возврат `{allocation, statistics: {}, bitmap (17 бит на UE), pdcch_stats}` (:966); вызывающий код результат отбрасывает (:1289), статистика уходит наружу через `StatsManager` → `get_stats()`.

## 7. Ограничения и открытые вопросы

- Ёмкость RB считается формулой RE·Qm·R, а не таблицами TBS TS 36.213 §7.1.7.2 (TODO в коде :1718, отклонение ~8–10% по оценке автора TODO, issue #30); таблица `CQI_TO_MCS` (:1680) смещена относительно TS 36.213 Table 7.2.3-1 (+2 индекса для CQI 5–13) — ёмкость систематически завышена (OPT-SCH-002); учёт CRS в первом слоте спорный (OPT-SCH-002).
- Учёт CCE — счётчик без позиций и поисковых пространств: проверяется только необходимое условие размещения (OPT-SCH-004); `release_cce` — заглушка (:1538), провал PDSCH после успешного PDCCH оставляет CCE занятыми до `reset_tti()` следующего TTI (BUG-SCH-005).
- HARQ не реализован (заготовка :335/:1201, поля гранта не используются, issue #27); QoS отсутствует (открытый PR #39); скользящее окно — проприетарное решение с TODO-альтернативами в docstring (:604).
- Поведенческие нюансы: двойное нулевое обновление EWMA у незапланированных UE (BUG-SCH-001, подтверждено замером), «залипание» двух счётчиков статистики в пустом TTI (BUG-SCH-004), сохранение устаревшего CQI при невалидном отчёте (BUG-SCH-002), потенциальный `ValueError` на этапе 7 при CQI=0 у UE с живым буфером (BUG-SCH-007, воспроизведён) — детали и статусы в [audit.md](docs/audit.md).
- Инфраструктура: тестовый набор на `dev` неработоспособен (BUG-SCH-008); CI в репозитории отсутствует.
- Открытые вопросы: кто должен потреблять возврат `schedule()` и зачем `statistics` всегда пуст (:1000, OPT-SCH-005); судьба незакрытых веток `feature/HARQ`, `feature/AMC`, `feature/drl-scheduler` относительно `dev` — требует отдельного уточнения.

## 8. Связанные материалы

- [Диаграммы](docs/diagrams.md) — контекст и классы (AS-IS), последовательность вызовов TTI, переходы состояний, черновик TO-BE
- [Ревизия](docs/audit.md) — 15 наблюдений (BUG-SCH-001…008, OPT-SCH-002…006, DOC-SCH-001…002) с доказательствами, замерами и статусами; таблица сопоставления прежних ID — там же
- [План развития](docs/features.md) — спецификации OPT-SCH-001, FEAT-SCH-001…007 и OPT-SCH-007, связи с issues/PR/ветками, межмодульные зависимости
- [Спецификация OPT-SCH-001](docs/specs/OPT-SCH-001.md) — план реализации разделения Ranker/Allocator (отдельный файл по DoD недели 5)
- [`Documentation/doc_scheduler_v2.1.0.md`](https://github.com/sherokiddo/project_py_scheduler/blob/ae9db40ecfd27787b4cdeba79bcb6eafabd7d44b/PyScheduler/Documentation/doc_scheduler_v2.1.0.md) — авторская документация модуля (PR #26)

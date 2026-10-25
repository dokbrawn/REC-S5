# SCHEDULER.py — планировщик радиоресурсов (LTE DL)

> Ответственный: Тимур (Scheduler)  
> Состояние: описан  
> Проверено по коду: `6c0aae2` | Обновлено: `2026-10-24`

Источник: [`PyScheduler/SCHEDULER.py`](https://github.com/sherokiddo/project_py_scheduler/blob/6c0aae2/PyScheduler/SCHEDULER.py), версия модуля v2.1.0 + QoS-слияние PR #39, 3245 строк. Ссылки даны в формате `файл::символ (:строка)`; номера строк действительны для коммита `6c0aae2` (HEAD ветки `dev`). Все приведённые числа и поведение проверены фактическими запусками на этом коммите; контрольный сценарий §4 воспроизводится побитово и на `ae9db40`, и на `6c0aae2`. Авторская документация модуля: [`Documentation/doc_scheduler_v2.1.0.md`](https://github.com/sherokiddo/project_py_scheduler/blob/6c0aae2/PyScheduler/Documentation/doc_scheduler_v2.1.0.md) (не обновлялась после PR #26, см. [audit.md](docs/audit.md) DOC-SCH-001).

## 1. Назначение

Модуль решает задачу MAC-планировщика downlink: один раз в TTI (1 мс) определяет, какие пользователи (UE) получат радиоресурс и какие именно группы ресурсных блоков (RBG) им достанутся — с учётом качества канала (CQI), заполненности буферов базовой станции и бюджета управляющего канала PDCCH (CCE). Реализованы восемь алгоритмов планирования (BestCQI, ProportionalFair, RoundRobin, три частотно-селективных FD-варианта и два QoS-алгоритма, слитых в PR #39), выбираемых через фабрику. Кроме принятия решения модуль пока сам исполняет его: извлекает пакеты из буфера BS и обновляет статистику throughput UE; расслоение запланировано самим кодом (roadmap-комментарий :3227–3245, см. [FEAT-SCH-009](docs/features.md#feat-sch-009)).

## 2. Границы ответственности

**Делает:**
- Полный pipeline одного TTI (этапы 0–8, `SCHEDULER.py::SchedulerInterface.schedule` :346): обновление карты CQI → отбор допущенных UE → скользящее окно → приоритеты → оценка потребности PDSCH → выделение CCE → распределение RBG → извлечение из буфера → статистика и результат.
- Восемь алгоритмов через фабрику `SchedulerInterface.create()` (:235): `'BestCQI'`, `'ProportionalFair'`, `'RoundRobin'`, `'FD_BCQI'`, `'FD_FGS'`, `'FD_PF'`, `'BasicQosAware'`, `'QosAware'` (ключи :262–263); список `available_algorithms()` (:277) расходится с ключами фабрики ([BUG-SCH-010](docs/audit.md#bug-sch-010)).
- Учёт бюджета CCE (`PDCCHManager` :1262) и перевод CQI в оценку ёмкости RB (`AdaptiveModulationAndCoding` :1703).
- Хранение CQI между отчётами (`CQIMap` :191), формирование грантов извлечения (`SchedulingGrant` :117), мультиплексирование логических каналов (`_logical_channel_multiplexing` :811, режимы Simple/Layered).
- Накопление статистики TTI: `get_stats()` (:438), `amc.get_stats()` (:1755), `pdcch_manager.get_stats()` (:1660).

**Не делает (относится к соседним модулям):**
- Не измеряет канал: `cqi`/`sbb_cqi` приходят готовыми из `UE_MODULE.py::GET_USERS_FOR_SCHEDULER` (:901), где формируются `UE_MODULE.py::SINR_TO_CQI` (:693).
- Не генерирует трафик и не владеет буферами: их хранит `BS_MODULE` (`IBufferManager` :472, реализации `SimpleBufferManager` :580 и `LayeredBufferManager` :1356); планировщик читает статус и извлекает по грантам.
- Не владеет ресурсной сеткой: занятие RB выполняет `RES_GRID.py::ALLOCATE_RBG` (:430, атомарно с откатом `RELEASE_RBG` :440).
- Не реализует HARQ: `harq_manager = None` (:341), `_get_harq_retransmissions` (:1231) — заготовка; поля гранта `ndi`/`rv`/`harq_process_id` не используются.
- Не реализует QoS/LCP-приоритеты: в Layered-режиме TB делится поровну между активными логическими каналами (комментарий в коде называет стратегию несправедливой, :861–863); QoS-планировщики слиты в `dev` в PR #39 (`6c0aae2`), LCP-приоритизация извлечения остаётся открытой ([FEAT-SCH-009](docs/features.md#feat-sch-009)).

## 3. Входы, выходы и зависимости

| Вход | Откуда | Формат/смысл |
|---|---|---|
| `tti: int` | `SIMULATION_MANAGER.py::run_tti` (:1657, вызов :1701) | номер текущего TTI (1 мс) |
| `users: List[Dict]` | `UE_MODULE.py::GET_USERS_FOR_SCHEDULER` (:901–920) | срез состояния на начало TTI, ровно 4 поля: `UE_ID`, `cqi` (WB 1–15), `sbb_cqi` (per-RBG список; **ключ с опечаткой — устоявшийся контракт обеих сторон**, [DOC-SCH-001](docs/audit.md#doc-sch-001)), `ue` (живая ссылка на объект UE) |
| размеры буферов | `BS_MODULE.py::IBufferManager.ue_has_buffer/get_buffer_status` (:530/:492) | читаются напрямую на этапе 1, дописываются в `users[i]['bs_buffer_size']` |
| `lte_grid`, `bs` | конструктор (:294); конфигурация — `SIMULATION_MANAGER.py::SchedulerConfig` (:1030) | `GET_RBG_SIZE` (:421), `GET_RBG_INDICES` (:424), `ALLOCATE_RBG` (:430), `GENERATE_BITMAP` (:567); `bs.buffer_manager`, `bs.use_simple_buffer` (:1696) |

| Выход | Куда | Формат/смысл |
|---|---|---|
| возврат `schedule()` | `SIMULATION_MANAGER` | `{allocation: {UE_ID: [freq_idx]}, statistics: {}, bitmap: {UE_ID: [17 бит]}, pdcch_stats}`; **в главном цикле результат отбрасывается**: `_ = self.run_tti(...)` (SIMULATION_MANAGER.py:1451), [OPT-SCH-005](docs/audit.md#opt-sch-005) |
| статистика | `StatsManager` (SIMULATION_MANAGER.py:109, `collect` :158) | фактический канал данных наружу: три `get_stats()` читают кэш `_last_*`, заполняемый на этапе 7.5 |
| извлечение пакетов | `BS_MODULE::get_packets(grants)` (:507, Layered :1441) | побочный эффект этапа 7: буфер BS физически уменьшается |
| per-QCI throughput | `BS_MODULE::QciThroughputTracker.update_all_qcis` (:223) | побочный эффект этапа 7 с `6c0aae2` (PR #39): `SCHEDULER.py` :901, :916–919, :941–944, :962–965, :967–975; на извлечение пакетов и гранты не влияет |
| throughput UE | `UE_MODULE.py::UPD_DL_THROUGHPUT_BPS` (:629) | побочный эффект этапа 7: `current_dl_throughput` и EWMA `average_throughput` (α=0.002 хардкод, :644; TODO «вывести в управление», issue #31) — знаменатель PF следующих TTI |
| занятые RB | `RES_GRID::ALLOCATE_RBG` (:430) | побочный эффект этапа 6: RBG заняты в обоих слотах подкадра до переиспользования (кадр = 10 подкадров) |

Зависимости: `GLOBALS` (`BITS_PER_BYTE` :140, `bytes_to_bits` :217), `time`, `dataclasses`, `typing`; runtime — RES_GRID, BS_MODULE, UE_MODULE, SIMULATION_MANAGER. Импорт `BaseStation` (:112) не используется ([OPT-SCH-006](docs/audit.md#opt-sch-006)).

## 4. Как проверить работу

**Минимальный сценарий** (проверен на `6c0aae2`, воспроизводится побитово и на `ae9db40`; сохранить как `PyScheduler/_check.py` и запустить `python3 _check.py` из каталога `PyScheduler/`, нужен numpy):

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

**Тесты:** `PyScheduler/tests/scheduler_tests/` — 27 тестовых функций (`test_scheduler_common.py`, `test_fd_best_cqi.py`, `test_fd_proportional_fair.py`, `test_fd_round_robin.py`) и бенчмарк `FD_benchmark.py`. Запуск — из каталога `PyScheduler/`: `python3 -m pytest tests/scheduler_tests/ -q` (из корня репозитория импорт `SCHEDULER` не разрешается: тесты добавляют в `sys.path` только каталог `tests/`, а модули проекта разрешаются через cwd). **Внимание: на `dev` набор сейчас неработоспособен** — отсутствует импортируемый всеми файлами модуль `log_utils` (есть только в ветках `multithread`/`feature/AMC`). Проверено на свежих чистых клонах `ae9db40` и `6c0aae2` — картина одинаковая: (A) как есть — 4 ошибки сборки независимо от каталога запуска; (B) после возврата `log_utils.py` — 15 failed / 12 passed (14 — устаревшее имя `'FD_RR'`, 1 — содержательный инвариант FD_PF); (C) после замены `'FD_RR'`→`'FD_FGS'` — 26 passed / 1 failed. Подробности: [BUG-SCH-008](docs/audit.md#bug-sch-008); восстановление набора — запрос к владельцу репозитория и автору тестового набора в [features.md](docs/features.md) §2 (в объём работ по модулю не входит).

## 5. Основные компоненты

| Файл / класс / функция | Назначение | Где используется |
|---|---|---|
| `SCHEDULER.py::SchedulingGrant` (:117) | dataclass гранта извлечения: `ue_id`, `num_bytes`, `lcid`, `ndi`, `harq_process_id`, `rv`; валидация `num_bytes ≥ 0`, `rv ∈ [0..3]` (:139); `to_dict()` (:160) | создаётся в `_logical_channel_multiplexing` (:811), потребляется `BS_MODULE::get_packets` (issue #27 — полная интеграция) |
| `SCHEDULER.py::CQIMap` (:191) | хранилище CQI на UE: `wb_cqi`, `sb_cqi` (per-RBG, длина = num_rbg), метки времени обновлений | пишет `_refresh_cqi` (:504), читают `_get_wb_cqi` (:1064) / `_get_sb_cqi` (:1084) |
| `SCHEDULER.py::SchedulerInterface` (:216) | оркестратор этапов 0–8 + фабрика: `create` (:235), `available_algorithms` (:277), `schedule` (:346), `get_stats` (:438), методы этапов (:504–1168), абстрактные `_calculate_priorities` (:1172) и `_allocate_pdsch` (:1197), HARQ-заготовка (:1231) | `SIMULATION_MANAGER` (создание :1357, вызов :1701) |
| `SCHEDULER.py::PDCCHManager` (:1262) | бюджет CCE: `_validate_parameters` (:1307), таблица `_calculate_total_cce` (:1347), `get_aggregation_level` (:1416), `check_cce_availability` (:1465), `allocate_cce` (:1496), `reset_tti` (:1545), `release_cce` — **заглушка** (:1568), `get_stats` (:1660) | этап 5 `_allocate_pdcch` (:769) |
| `SCHEDULER.py::AdaptiveModulationAndCoding` (:1703) | `CQI_TO_MCS` (:1709), `GET_BITS_PER_RB` (:1730) — единственная точка перевода CQI в биты (этапы 4.5, 6, 7, статистика); `get_stats` (:1755) читает кэш `_last_*` планировщика | весь модуль; TODO замены на TBS-таблицы :1749 (issue #30) |
| `BestCQIScheduler` (:1877) | priority = WB CQI (:1908); жадное TD-распределение (:1931) | фабрика `'BestCQI'` |
| `RoundRobinScheduler` (:1985) | ротация очереди от `rr_ue_offset` (:2015); по 1 RBG каждому по кругу (:2040); оценка PDSCH — pass-through (:1996) | фабрика `'RoundRobin'` |
| `ProportionalFairScheduler` (:2103) | priority = `instant_rate / (average_throughput/1000)` (:2118, fallback при нулевой истории :2135); жадное TD (:2160) | фабрика `'ProportionalFair'` |
| `FDxBestCQIScheduler` (:2215) | на каждом RBG побеждает max SB CQI с fallback на WB (:2269, выбор :2304) | фабрика `'FD_BCQI'` |
| `FDxFairGreedyScheduler` (:2339) | RR-ротация в TD (:2394) + per-RBG выбор по SB CQI с ограничением «один UE — один RBG за раунд» (`served_in_round` :2448–2505); до ревью PR #26 класс носил имя FD_RR | фабрика `'FD_FGS'` |
| `FDxProportionalFairScheduler` (:2524) | WB PF задаёт порядок выдачи CCE (:2588); на каждом RBG побеждает max PF-метрики по SB CQI (:2631, цикл :2645) | фабрика `'FD_PF'` |
| `BasicQosAwareScheduler` (:2704) | QoS (PR #39): ранжирование — HOL-группировка потоков + GBR-приоритет `1_000_000 + best_gbr_group` (:2764–2802); per-RBG выбор — произведение `hol_delay × gbr_weight × cqa_metric` (:2930; Coita или PF по `metric_mode`); docstring предупреждает: один bearer на UE | фабрика `'BasicQosAware'` (:262) |
| `QosAwareScheduler` (:2960) | QoS (PR #39): приоритет по потокам (UE, QCI): GBR — масштабное смещение + urgency от HOL delay и packet delay budget (`QCI.get_delay_budget`), per-RBG выбор потока по метрике `sigmoid(hol, pdb) × pf` (:3128–3133); переопределяет `_logical_channel_multiplexing` (:3175–3222) | фабрика `'QosAware'` (:263) |
| roadmap-комментарий (:3227–3245) | планы из самого кода: BufferManager, DCI + AllocationTracker, каноничный output, QoS, tie-break, исследование венгерского/жадного распределения RBG, оценка средней пропускной способности PF, защита голодающих UE | основа [features.md](docs/features.md) |

Матрица переопределений (различия алгоритмов локальны — базовый класс реализует весь цикл):

| Планировщик | `_calculate_priorities` | `_apply_pdsch_estimation` | `_allocate_pdsch` | доп. состояние |
|---|---|---|---|---|
| BestCQI (:1877) | WB CQI (:1908) | базовый, порог 95% (:712) | жадный TD (:1931) | — |
| RoundRobin (:1985) | ротация очереди (:2015) | pass-through (:1996) | 1 RBG по кругу (:2040) | `rr_rbg_offset`, `rr_ue_offset` |
| ProportionalFair (:2103) | r/R (:2118) | базовый (95%) | жадный TD (:2160) | — |
| FD_BCQI (:2215) | WB CQI (:2250) | pass-through (:2243) | per-RBG max SB CQI (:2269) | — |
| FD_FGS (:2339) | RR-ротация (:2394) | pass-through (:2377) | per-RBG SB CQI + `served_in_round` (:2423) | `rr_*_offset` |
| FD_PF (:2524) | WB PF (:2588) | pass-through (:2571) | per-RBG PF по SB CQI (:2631) | — |
| BasicQosAware (:2704) | HOL-группировка + GBR-приоритет (:2764–2802) | pass-through (:2753) | per-RBG произведение hol×gbr×cqa (:2930) | `metric_mode` (Coita/PF) |
| QosAware (:2960) | per-flow GBR/urgency (:2999–3038) | pass-through (:2988) | per-RBG выбор потока (:3044, метрика :3128–3133) | `allocation_flow`, override мультиплексирования (:3175–3222) |

Ключевые константы (дефолты `__init__` :294 и пороговые значения): `pcfich=2`; `max_dl_ue_tti=None` (без лимита); `window_size=100`, `enable_window=True`; `wb/sb_cqi_upd_interval=1` (каждый TTI); порог оценки PDSCH 95% `rb_per_slot` (:733); aggregation level: CQI 13–15→1, 10–12→2, 7–9→4, 1–6→8 CCE (:1416); бюджет CCE при 10 МГц: PCFICH 1/2/3 → 8/25/41 (:1347); RBG при 10 МГц: 3 RB → 17 RBG (`RES_GRID.py::RBG_SIZE_TABLE` :293); bits/RB (PCFICH=2, 1 порт): CQI 15→798, 13→755, 7→326 (:1730).

## 6. Один типичный сценарий

Вызов `schedule(tti=5, users)` из `SIMULATION_MANAGER.run_tti()` (BestCQI, 10 МГц, сценарий раздела 4 — все числа из фактического прогона на `ae9db40`):

1. **Этап 0** `_refresh_cqi` (:504) — WB CQI 13/7/15 записаны в `cqi_map` (SB-списки пусты — TD-сценарий).
2. **Этап 1** `_filter_eligible_ues` (:559) — все трое допущены (буферы существуют и непустые, CQI валидны); побочно: **всем** users сброшен `ue.current_dl_throughput = 0`, дописан `bs_buffer_size` = 1000/5000/300.
3. **Этапы 2–4** — окно: `_ue_queue` = [1,2,3] с ротацией (:610/:653); приоритеты = WB CQI; `priority_list` = [3, 1, 2] (:684).
4. **Этап 4.5** `_apply_pdsch_estimation` (:712) — потребность: UE3 = 2400//798 = 3 RB, UE1 = 8000//755 = 10 RB, UE2 = min(40000//326, 50) = 50 RB; с UE2 сумма 63 ≥ порога 47.5 → **UE2 отсечён** («13/50 RB = 26.0%, 1 UE excluded»), CCE не тратит.
5. **Этап 5** `_allocate_pdcch` (:769) — `reset_tti()`, CQI 15/13 ∈ [13–15] → по 1 CCE в порядке priority-списка: `{3: 1, 1: 1}`, занято 2 из 25 (8%).
6. **Этап 6** `_allocate_pdsch` (:1931) — жадно: RBG 0–1 → UE3 (остаток буфера исчерпан), RBG 2–5 → UE1; `allocation = {1: [6..17], 2: [], 3: [0..5]}`, 18 из 50 RB; каждый RBG занят атомарно через `ALLOCATE_RBG` (оба слота, откат при неудаче).
7. **Этап 7** `_process_buffers` (:880) — вместимость по WB CQI (UE1: 12·755 = 9060 бит → 1132 B; UE3: 6·798 = 4788 бит → 598 B) → гранты `SchedulingGrant` → `get_packets` извлекает 1000 B и 300 B → `UPD_DL_THROUGHPUT_BPS`: 8004 и 2404 бита (включая остаток `max_bits mod 8`, помеченный в коде «временный костыль» :934), EWMA-среднее 16008/4808 бит/с; с `6c0aae2` здесь же обновляется `qci_tput_tracker` (:967–975), а ветки «не запланирован»/«нет вместимости» завершаются `continue` (:919, :944) — один нулевой шаг EWMA вместо двух ([BUG-SCH-001](docs/audit.md#bug-sch-001) закрыт).
8. **Этапы 7.5–8** — счётчики в `_last_*` (:1104/:1154); возврат `{allocation, statistics: {}, bitmap (17 бит на UE), pdcch_stats}` (:996); вызывающий код результат отбрасывает (:1451), статистика уходит наружу через `StatsManager` → `get_stats()`.

## 7. Ограничения и открытые вопросы

- Ёмкость RB считается формулой RE·Qm·R, а не таблицами TBS TS 36.213 §7.1.7.2 (TODO в коде :1749, отклонение ~8–10% по оценке автора TODO, issue #30); таблица `CQI_TO_MCS` (:1709) смещена относительно TS 36.213 Table 7.2.3-1 (+2 индекса для CQI 5–13) — ёмкость систематически завышена ([OPT-SCH-002](docs/audit.md#opt-sch-002)); учёт CRS в первом слоте спорный (там же).
- Учёт CCE — счётчик без позиций и поисковых пространств: проверяется только необходимое условие размещения ([OPT-SCH-004](docs/audit.md#opt-sch-004)); `release_cce` — заглушка (:1568), провал PDSCH после успешного PDCCH оставляет CCE занятыми до `reset_tti()` следующего TTI ([BUG-SCH-005](docs/audit.md#bug-sch-005)).
- HARQ не реализован (заготовка :341/:1231, поля гранта не используются, issue #27); QoS-планировщики слиты в `dev` в PR #39 (`6c0aae2`: `BasicQosAwareScheduler` :2704, `QosAwareScheduler` :2960, ключи фабрики :262–263), LCP-приоритизация в извлечении пакетов по QCI остаётся открытой частью FEAT-SCH-009; скользящее окно — проприетарное решение с TODO-альтернативами в docstring (:610).
- Поведенческие нюансы: двойное нулевое обновление EWMA у незапланированных UE существовало до `6c0aae2` ([BUG-SCH-001](docs/audit.md#bug-sch-001), закрыт побочно с qci-трекером PR #39 — проверено замером), «залипание» двух счётчиков статистики в пустом TTI ([BUG-SCH-004](docs/audit.md#bug-sch-004)), сохранение устаревшего CQI при невалидном отчёте ([BUG-SCH-002](docs/audit.md#bug-sch-002)), крах этапа 7 при CQI=0 у UE с живым буфером воспроизводился на `ae9db40`, на `6c0aae2` через `schedule()` недостижим ([BUG-SCH-007](docs/audit.md#bug-sch-007)), откат `ALLOCATE_RBG` освобождает RB без проверки владельца ([BUG-SCH-009](docs/audit.md#bug-sch-009), воспроизведено), `available_algorithms()` (:277) возвращает два имени, которые фабрика не принимает ([BUG-SCH-010](docs/audit.md#bug-sch-010)) — детали и статусы в [audit.md](docs/audit.md).
- Инфраструктура: тестовый набор на `dev` неработоспособен ([BUG-SCH-008](docs/audit.md#bug-sch-008)); CI в репозитории отсутствует.
- Открытые вопросы: кто должен потреблять возврат `schedule()` и зачем `statistics` всегда пуст (:1030, [OPT-SCH-005](docs/audit.md#opt-sch-005)); судьба незакрытых веток `feature/HARQ`, `feature/AMC`, `feature/drl-scheduler` относительно `dev` — требует отдельного уточнения.

## 8. Связанные материалы

- [Диаграммы](docs/diagrams.md) — контекст и классы (AS-IS), последовательность вызовов TTI, переходы состояний, черновик TO-BE
- [Ревизия](docs/audit.md) — 18 наблюдений (BUG-SCH-001…011, OPT-SCH-002…006, DOC-SCH-001…002) с доказательствами, замерами и статусами; таблица сопоставления прежних ID — там же
- [План развития](docs/features.md) — карточки FEAT-SCH-001…009 (две из них — крупные архитектурные разработки: FEAT-SCH-008 с отдельной спецификацией и FEAT-SCH-009 в статусе черновика), связи с issues/PR/ветками, межмодульные зависимости
- [Спецификация SPEC-FEAT-SCH-008](docs/specs/SPEC-FEAT-SCH-008.md) — план реализации разделения Ranker/Allocator (v4): контракты (включая `MultiplexingPolicy` и propose→validate→commit), правила миграции R1–R8, атомарные зелёные шаги M0–M8 (M4c/M4d, M5a/M5b, M8a–M8e), CQI-трек C0–C4, регрессионная матрица
- [Definition of Done](docs/process/DOD-FEAT-SCH-008.md) — критерии готовности атомарного PR (SPEC §2 + практика ревью репозитория), gate шага, статус выполнения M0 с подтверждениями
- [ROADMAP](docs/process/ROADMAP-SCH.md) — статус пунктов развития: TODO-список из кода (:3227–3245), шаги M0–M8e и CQI-трек, смежные issues, закрытые и открытые пункты
- [CHANGELOG](docs/process/CHANGELOG-DOC-SCH-001.md) — ревизии комплекта DOC-SCH-001 (1–9) и работы FEAT-SCH-008 вне комплекта
- [`Documentation/doc_scheduler_v2.1.0.md`](https://github.com/sherokiddo/project_py_scheduler/blob/6c0aae2/PyScheduler/Documentation/doc_scheduler_v2.1.0.md) — авторская документация модуля (PR #26, после не обновлялась)

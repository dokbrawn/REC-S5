# Диаграммы модуля SCHEDULER.py

> Ответственный: Тимур (Scheduler) | Проверено по коду: `ae9db40` (ветка `dev`)  
> Все схемы соответствуют коммиту `ae9db40`; поведение подтверждено чтением кода и фактическими прогонами (сценарий TTI 5 из [README §4](../README.md), pytest). Наблюдения, упомянутые на схемах (BUG/OPT/DOC-SCH-xxx), — в [audit.md](audit.md); планируемые изменения (FEAT/OPT-SCH-xxx) — в [features.md](features.md).

## 1. Текущая структура (AS-IS)

Кратко: показаны границы модуля, его внутренний состав и структура классов; каждое соединение подтверждено кодом (ссылки в §4) и прогоном сценария TTI 5.

### 1.1. Контекст модуля: границы и побочные эффекты

```mermaid
flowchart LR
    SM["SIMULATION_MANAGER<br/>run_tti :1491"] -->|"users: UE_ID, cqi, sbb_cqi, ue<br/>(срез на начало TTI, :1534)"| SCH["SCHEDULER.py<br/>schedule(tti, users) :340"]
    SCH -->|"возврат {allocation, statistics, bitmap,<br/>pdcch_stats} — отбрасывается (:1289)"| SM
    STATS["StatsManager :108<br/>collect :156"] -->|"scheduler.get_stats() :432,<br/>amc.get_stats() :1725,<br/>pdcch_manager.get_stats() :1630<br/>— читают кэш _last_*"| SCH

    UE["UE_MODULE<br/>GET_USERS_FOR_SCHEDULER :901"] -.->|"формирует список users"| SM
    SCH -->|"этап 1: сброс current_dl_throughput = 0 (:565)<br/>этап 7: UPD_DL_THROUGHPUT_BPS :629 (EWMA α=0.002)"| UEOBJ["объекты UE"]
    SCH -->|"этап 1: ue_has_buffer :318,<br/>get_buffer_status :280"| BS["BS_MODULE<br/>IBufferManager :260<br/>(Simple :368 / Layered :1113)"]
    SCH -->|"этап 7: get_packets(grants) :295 —<br/>физическое извлечение пакетов"| BS
    SCH -->|"этап 6: ALLOCATE_RBG :430 (атомарно,<br/>откат RELEASE_RBG :440); этап 8: GENERATE_BITMAP :567"| GRID["RES_GRID<br/>lte_grid"]
    SCH -->|"bytes_to_bits :201,<br/>BITS_PER_BYTE :140"| GL["GLOBALS"]
```

### 1.2. Внутренний состав модуля

```mermaid
flowchart TD
    SI["SchedulerInterface :214<br/>(оркестратор этапов 0–8 + фабрика create :233)"]
    PDM["PDCCHManager :1232<br/>бюджет CCE, aggregation level,<br/>release_cce — заглушка :1538"]
    AMC["AdaptiveModulationAndCoding :1673<br/>CQI_TO_MCS :1680, GET_BITS_PER_RB :1700"]
    CQM["CQIMap :189<br/>wb_cqi, sb_cqi (per-RBG), метки времени"]
    SG["SchedulingGrant :115<br/>ue_id, num_bytes, lcid,<br/>ndi, harq_process_id, rv"]
    SI -->|композиция| PDM
    SI -->|композиция| AMC
    SI -->|"агрегация: cqi_map"| CQM
    SI -.->|создаёт на этапе 7| SG
```

### 1.3. UML классов

```mermaid
classDiagram
    class SchedulerInterface {
        +lte_grid
        +amc
        +pdcch_manager
        +cqi_map
        +create(algorithm, lte_grid, bs)
        +schedule(tti, users) Dict
        +get_stats() Dict
        #_refresh_cqi()
        #_filter_eligible_ues()
        #_update_active_window()
        #filter_by_window()
        #_form_priority_list()
        #_apply_pdsch_estimation()
        #_allocate_pdcch()
        #_logical_channel_multiplexing()
        #_process_buffers()
        #_calculate_priorities()*
        #_allocate_pdsch()*
    }
    class BestCQIScheduler {
        #_calculate_priorities() priority = WB CQI
        #_allocate_pdsch() жадный TD
    }
    class RoundRobinScheduler {
        +rr_rbg_offset
        +rr_ue_offset
        #_calculate_priorities() ротация очереди
        #_apply_pdsch_estimation() pass-through
        #_allocate_pdsch() 1 RBG по кругу
    }
    class ProportionalFairScheduler {
        #_calculate_priorities() r/R
        #_allocate_pdsch() жадный TD
    }
    class FDxBestCQIScheduler {
        #_allocate_pdsch() per-RBG max SB CQI
    }
    class FDxFairGreedyScheduler {
        +rr_rbg_offset
        +rr_ue_offset
        #_allocate_pdsch() per-RBG + served_in_round
    }
    class FDxProportionalFairScheduler {
        #_allocate_pdsch() per-RBG PF по SB CQI
    }
    class PDCCHManager {
        +total_cce
        +max_dl_cce
        +num_assigned_cce
        +get_aggregation_level(cqi)
        +allocate_cce(ue_id, n)
        +reset_tti()
        +release_cce(ue_id) заглушка
        +get_stats()
    }
    class AdaptiveModulationAndCoding {
        +CQI_TO_MCS
        +GET_BITS_PER_RB(cqi)
        +get_stats()
    }
    class CQIMap {
        +wb_cqi
        +sb_cqi
        +last_wb_update
        +last_sb_update
    }
    class SchedulingGrant {
        +ue_id
        +num_bytes
        +lcid
        +ndi
        +rv
        +to_dict()
    }
    SchedulerInterface <|-- BestCQIScheduler
    SchedulerInterface <|-- RoundRobinScheduler
    SchedulerInterface <|-- ProportionalFairScheduler
    SchedulerInterface <|-- FDxBestCQIScheduler
    SchedulerInterface <|-- FDxFairGreedyScheduler
    SchedulerInterface <|-- FDxProportionalFairScheduler
    SchedulerInterface *-- PDCCHManager
    SchedulerInterface *-- AdaptiveModulationAndCoding
    SchedulerInterface o-- CQIMap : cqi_map
    SchedulerInterface ..> SchedulingGrant : создаёт на этапе 7
```

## 2. Типовой сценарий (AS-IS)

Сценарий: один TTI — вызов `schedule(tti, users)` из `SIMULATION_MANAGER.run_tti()`, включая все выходы за границы модуля. Порядок этапов подтверждён кодом :340–430 и прогоном ([README §4](../README.md)).

### 2.1. Последовательность вызовов

```mermaid
sequenceDiagram
    participant SIM as SIMULATION_MANAGER
    participant SCH as schedule()
    participant CQI as cqi_map
    participant BS as BS_MODULE (буферы)
    participant PD as PDCCHManager
    participant GR as RES_GRID
    participant UE as UE_MODULE

    SIM->>SCH: schedule(tti, users) :1535
    SCH->>CQI: 0 _refresh_cqi :498 — записать WB/SB CQI
    SCH->>BS: 1 ue_has_buffer + get_buffer_status :553
    BS-->>SCH: размеры буферов → bs_buffer_size
    SCH->>UE: 1 current_dl_throughput = 0 (всем users) :565
    SCH->>SCH: 2–4 окно :604/:647 → приоритеты* → priority_list :678
    SCH->>SCH: 4.5 оценка PDSCH :706 (порог 95%)
    SCH->>PD: 5 reset_tti :1515 + allocate_cce :1466 (CQI → 1/2/4/8 CCE)
    PD-->>SCH: ues_with_pdcch
    loop каждый RBG (внутри _allocate_pdsch*)
        SCH->>GR: 6 ALLOCATE_RBG(tti, rbg_idx, ue_id) :430
        GR-->>SCH: True / False (при неудаче откат RELEASE_RBG :440)
    end
    SCH->>SCH: 7 вместимость RB → SchedulingGrant :805
    SCH->>BS: 7 get_packets(grants) :295 — извлечение пакетов
    BS-->>SCH: (packets, total_bytes)
    SCH->>UE: 7 UPD_DL_THROUGHPUT_BPS(bits, 1 ms) :629
    SCH->>GR: 8 GENERATE_BITMAP(tti, ue_id) :567
    SCH->>PD: 8 get_stats() :1630
    SCH-->>SIM: {allocation, statistics, bitmap, pdcch_stats}
```

Звёздочкой помечены виртуальные методы — две точки расхождения шести алгоритмов (`_calculate_priorities` :1142, `_allocate_pdsch` :1167).

### 2.2. Досрочные выходы (dataflow с ветвлениями)

```mermaid
flowchart TD
    A["schedule(tti, users)"] --> B["0 _refresh_cqi :498"]
    B --> C["1 _filter_eligible_ues :553"]
    C -->|пусто| Z["_empty_result :1007<br/>(счётчики blocked/avg_priority<br/>не сбрасываются — BUG-SCH-004)"]
    C --> D["2/2.5 окно :604/:647"]
    D -->|пусто| Z
    D --> E["3 _calculate_priorities* :1142"]
    E --> F["4 _form_priority_list :678"]
    F -->|пусто| Z
    F --> G["4.5 _apply_pdsch_estimation :706"]
    G --> H["5 _allocate_pdcch :763"]
    H -->|пусто| Z
    H --> I["6 _allocate_pdsch* :1167"]
    I --> J["7 _process_buffers :874"]
    J --> K["7.5 _update_stats :1074"]
    K --> L["8 _build_result :966"]
    Z --> M["возврат в SIMULATION_MANAGER<br/>(в главном цикле отбрасывается :1289)"]
    L --> M
```

### 2.3. Контур обратной связи между TTI

Проверен замером: заранее выставленный `average_throughput` = 1 000 000 у незапланированного UE затухает до 996 004 за один TTI — двойной нулевой шаг EWMA ([audit.md](audit.md), BUG-SCH-001).

```mermaid
flowchart LR
    CH["Модель канала<br/>SINR_TO_CQI :693 → ue.cqi / cqi_subband"] --> CQ["cqi_map (_refresh_cqi :498)"]
    CQ --> PR["Приоритеты (этап 3) + AMC :1700"]
    TR["Трафик → буфер BS"] --> EL["Eligibility :553 + оценка :706"]
    PR --> AL["_allocate_pdsch :1167*"]
    EL --> AL
    AL --> BUF["get_packets :295 — буфер уменьшается"]
    BUF --> EW["UPD_DL_THROUGHPUT_BPS :629<br/>EWMA average_throughput (α=0.002 :644)"]
    EW -->|"знаменатель PF следующего TTI"| PR
    AL --> GRID["RES_GRID: RB заняты до переиспользования подкадра"]
    AL --> ST["_last_* :1074 → get_stats() :432 → StatsManager"]
```

### 2.4. Переходы состояний: жизненный цикл записи CQIMap (на UE)

Заявленный в docstring `CQIMap` (:195–199) жизненный цикл против фактического поведения кода:

```mermaid
stateDiagram-v2
    [*] --> Нет_записи : UE ещё не присылал валидный отчёт
    Нет_записи --> Created : первый валидный WB CQI 1–15<br/>_refresh_cqi :523
    Created --> Updated : новый валидный отчёт<br/>wb_cqi, last_wb_update = tti :533
    Updated --> Updated : невалидный CQI или пустой sbb_cqi —<br/>запись НЕ затирается (BUG-SCH-002) :521
    Updated --> Deleted : дерегистрация UE<br/>НЕ РЕАЛИЗОВАНО — только в docstring :198
    Created --> Deleted
    Deleted --> [*]
    note right of Updated
        _get_wb_cqi :1034 для UE без записи
        возвращает 0 — этап 1 отсеивает его,
        но этап 7 при живом буфере падает
        ValueError (BUG-SCH-007)
    end note
```

### 2.5. Переходы состояний: бюджет CCE в пределах одного TTI (PDCCHManager)

```mermaid
stateDiagram-v2
    [*] --> Свободен : reset_tti() в начале этапа 5 :1515
    Свободен --> Выделен : allocate_cce(ue_id, L) успех :1466<br/>num_assigned_cce += L, cce_allocations[ue_id] = L
    Выделен --> Выделен : повторный запрос тому же UE → False :1490
    Свободен --> Свободен : бюджет исчерпан → False :1435
    Выделен --> Утёк : PDSCH для UE не разместились —<br/>release_cce() заглушка :1538 (BUG-SCH-005)
    Утёк --> Свободен : только reset_tti() следующего TTI
```

### 2.6. Переходы состояний: UE в скользящем окне (`_ue_queue`)

```mermaid
stateDiagram-v2
    [*] --> В_очереди : новый eligible UE<br/>_update_active_window extend :637
    В_очереди --> В_окне : позиция < window_size (100)<br/>filter_by_window :662
    В_окне --> В_очереди : ротация обработанных в конец :668
    В_очереди --> Исключён : UE пропал из eligible<br/>(буфер пуст / CQI невалиден) :639
    Исключён --> В_очереди : UE снова eligible
    Исключён --> [*] : очередь переживает TTI
```

## 3. Целевая структура (TO-BE) — только если согласована

Не согласовано, см. [features.md](features.md) (OPT-SCH-001). Направление «разделить ранжирование пользователей и аллокацию ресурсов» следует из roadmap модуля (:2676–2694) и наблюдаемого дублирования механики аллокации в шести `_allocate_pdsch`; ниже — черновик схемы, шаги и приёмка описаны в OPT-SCH-001.

```mermaid
classDiagram
    class SchedulerInterface {
        +create(config) фабрика пар ranker+allocator
        +schedule(tti, users) Dict
        +get_stats() Dict
        -ranker: UserRanker
        -allocator: ResourceAllocator
    }
    class UserRanker {
        <<interface>>
        +rank(windowed_ues, ctx) priority_list
    }
    class ResourceAllocator {
        <<interface>>
        +allocate(tti, ues_with_pdcch, ctx) allocation
        +rollback(ue_id) откат гранта
    }
    class BestCQIRanker
    class ProportionalFairRanker
    class RoundRobinRanker
    class TDGreedyAllocator {
        жадный TD
    }
    class RRCyclicAllocator {
        1 RBG по кругу
    }
    class FDPerRBGAllocator {
        per-RBG турнир по SB CQI
    }
    UserRanker <|-- BestCQIRanker
    UserRanker <|-- ProportionalFairRanker
    UserRanker <|-- RoundRobinRanker
    ResourceAllocator <|-- TDGreedyAllocator
    ResourceAllocator <|-- RRCyclicAllocator
    ResourceAllocator <|-- FDPerRBGAllocator
    SchedulerInterface o-- UserRanker : стратегия
    SchedulerInterface o-- ResourceAllocator : стратегия
    SchedulerInterface *-- PDCCHManager : + рабочий release_cce (FEAT-SCH-001)
    SchedulerInterface *-- AdaptiveModulationAndCoding : TBS-таблицы 36.213 (FEAT-SCH-002)
```

Что изменится относительно AS-IS: общая механика аллокации (`remaining_buffer`, вызов `ALLOCATE_RBG`, сборка индексов RB, условия прерывания), продублированная сейчас в шести `_allocate_pdsch`, уходит в иерархию `ResourceAllocator`; выбор UE — в иерархию `UserRanker`; базовый класс остаётся оркестратором этапов. Старые имена фабрики (`'BestCQI'`, `'FD_PF'`, …) сохраняются как пары (ranker, allocator) для обратной совместимости с `SchedulerConfig` (SIMULATION_MANAGER.py:871). В ту же схему без изменения оркестратора встраиваются: QoS-планировщики из открытого PR #39 (`QosAwareScheduler` — ещё один Ranker), DRL-ранжирование из ветки `feature/drl-scheduler` (PPO/DQN-ranker), венгерский бенчмарк (FEAT-SCH-004 — офлайн эталонный Allocator).

## 4. Ссылки на исходники

- `PyScheduler/SCHEDULER.py::SchedulerInterface.schedule` (:340–430) — порядок этапов 0–8, досрочные выходы через `_empty_result` (:1007)
- `PyScheduler/SCHEDULER.py::SchedulerInterface.create` (:233) — фабрика шести алгоритмов
- `PyScheduler/SCHEDULER.py::_refresh_cqi` (:498, SB-часть :540) — поведение карты CQI, невалидные отчёты игнорируются
- `PyScheduler/SCHEDULER.py::PDCCHManager.allocate_cce/release_cce/reset_tti` (:1466/:1538/:1515) — учёт CCE и заглушка освобождения
- `PyScheduler/SCHEDULER.py::AdaptiveModulationAndCoding.GET_BITS_PER_RB` (:1700) — CQI → биты/RB, TODO TBS-таблиц :1718
- `PyScheduler/SIMULATION_MANAGER.py::run_tti` (:1491), создание планировщика (:1196), `SchedulerConfig` (:871), отброшенный результат (:1289), `StatsManager` (:108, collect :156)
- `PyScheduler/UE_MODULE.py::GET_USERS_FOR_SCHEDULER` (:901–919) — контракт входа `users`, ключ `sbb_cqi` (:915)
- `PyScheduler/UE_MODULE.py::UPD_DL_THROUGHPUT_BPS` (:629, EWMA α=0.002 :644), `SINR_TO_CQI` (:693, клампит 1–15)
- `PyScheduler/BS_MODULE.py::IBufferManager` (:260; get_buffer_status :280, get_packets :295, ue_has_buffer :318), `LayeredBufferManager` (:1113), `BaseStation.use_simple_buffer` (:1439)
- `PyScheduler/RES_GRID.py::ALLOCATE_RBG/RELEASE_RBG/GET_RBG_INDICES/GET_RBG_SIZE/GENERATE_BITMAP` (:430/:440/:424/:421/:567), `BANDWIDTH_TO_RB` (:283), `RBG_SIZE_TABLE` (:293)
- `PyScheduler/GLOBALS.py::bytes_to_bits` (:201), `BITS_PER_BYTE` (:140)

Правила: схемы хранить **текстом Mermaid** в Markdown; AS-IS и TO-BE не смешивать; не рисовать каждую функцию; схема должна соответствовать конкретному коммиту.

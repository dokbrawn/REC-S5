"""
Week 02 · Сценарий для отчёта: полный scheduling cycle за один TTI.
Сценарий: BestCQI, 10 МГц, 3 UE, TTI 5. Все числа отчёта получены этим прогоном.

Запуск (нужен numpy):
    PYSCHEDULER_PATH=<путь до папки PyScheduler из project_py_scheduler@dev> \
        python3 scenario_tti5.py

Если переменная не задана, ищется ../project_py_scheduler/PyScheduler рядом с репозиторием отчёта.
"""
import sys, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT = os.path.normpath(os.path.join(HERE, '..', '..', '..', 'project_py_scheduler', 'PyScheduler'))
PYSCHED = os.environ.get('PYSCHEDULER_PATH', DEFAULT)
if not os.path.isdir(PYSCHED):
    sys.exit(f'Не найдена папка PyScheduler: {PYSCHED}\nЗадайте PYSCHEDULER_PATH=<путь до PyScheduler>')
sys.path.insert(0, PYSCHED)

import GLOBALS
from RES_GRID import RES_GRID_LTE
from BS_MODULE import BaseStation
from UE_MODULE import UserEquipment
from TRAFFIC_MODEL import Packet
from SCHEDULER import SchedulerInterface

GLOBALS.CURRENT_TIME = 5
TTI = 5
BW = 10

# --- сборка стенда (как в SIMULATION_MANAGER.RUN) ---
bs = BaseStation(bandwidth=BW, use_simple_buffer=True)
grid = RES_GRID_LTE(bandwidth=BW, num_frames=2)

ue_defs = [  # (id, cqi, x_м, байт в пакете)
    (1, 13, 300, 1000),
    (2, 7,  800, 5000),
    (3, 15, 100, 300),
]
ues = {}
for ueid, cqi, dist, nbytes in ue_defs:
    ue = UserEquipment(UE_ID=ueid, x=float(dist), y=0.0)
    ue.cqi = cqi
    ue.cqi_subband = []          # TD-сценарий, без subband-отчётов
    ues[ueid] = ue
    bs.buffer_manager.create_ue_buffer(ueid, bs.per_ue_max)
    bs.buffer_manager.add_packet(ueid, Packet(size=nbytes, ue_id=ueid, creation_time=0))

# вход планировщика — ровно то, что делает GET_USERS_FOR_SCHEDULER (UE_MODULE.py:901)
users = [{"UE_ID": u.UE_ID, "cqi": u.cqi, "sbb_cqi": u.cqi_subband, "ue": u}
         for u in ues.values()]


def dump_state(tag):
    print(f"\n===== {tag} =====")
    for ueid in sorted(ues):
        ue = ues[ueid]
        st = bs.buffer_manager.get_buffer_status(ueid)
        buf = sum(s.buffer_size for s in st)
        print(f"UE{ueid}: cqi={ue.cqi} buffer={buf}B "
              f"cur_tput={ue.current_dl_throughput:.0f} avg_tput={ue.average_throughput:.2f} "
              f"last_bits={ue.last_transmitted_bits} total_bits={ue.total_dl_transmitted_bits}")


dump_state("ДО schedule()")

sched = SchedulerInterface.create('BestCQI', grid, bs,
                                  pcfich=2, enable_window=True,
                                  window_size=100, verbose=True)
print("\n===== ВЫЗОВ schedule(5, users) — VERBOSE ЛОГ =====")
result = sched.schedule(TTI, users)

print("\n===== РЕЗУЛЬТАТ =====")
print("allocation:", json.dumps({str(k): v for k, v in result['allocation'].items()}))
print("bitmap:", json.dumps({str(k): v for k, v in result['bitmap'].items()}))
print("pdcch_stats:", json.dumps(result['pdcch_stats'], default=str))
print("statistics:", result['statistics'])

dump_state("ПОСЛЕ schedule()")

print("\n===== users dict после TTI (поля, добавленные планировщиком) =====")
for u in users:
    print({k: v for k, v in u.items() if k != 'ue'})

print("\n===== scheduler.get_stats() =====")
st = sched.get_stats()
for k, v in st.items():
    if k == 'sch_priority_list':
        print(f"{k}: [ {', '.join(str((u['UE_ID'], u['priority'])) for u in v)} ]")
    else:
        print(f"{k}: {json.dumps(v, default=str) if isinstance(v, (dict, list)) else v}")

print("\n===== amc.get_stats() =====")
print(json.dumps(sched.amc.get_stats(), default=str, indent=1))

print("\n===== состояние cqi_map =====")
for ueid, e in sched.cqi_map.items():
    print(ueid, e)

print("\n===== сетка: кто занял RB (подкадр 5) =====")
for slot in [0, 1]:
    row = []
    for f in range(grid.rb_per_slot):
        rb = grid.GET_RB(TTI, f"sub_{TTI % 10}_slot_{slot}", f)
        row.append(rb.UE_ID if rb and rb.UE_ID else '.')
    print(f"slot{slot}:", row)

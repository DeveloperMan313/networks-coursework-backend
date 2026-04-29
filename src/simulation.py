import asyncio
from asyncio.tasks import Task
from typing import List, Never, Tuple

from src.application import PC_app

PC_CNT = 3

_pc_ring: List[PC_app] = []

_phy_ticks_task: Task[Never] | None = None
_app_ticks_task: Task[Never] | None = None


def init_network():
    for i in range(PC_CNT):
        _pc_ring.append(PC_app(f"PC{i}"))

    for i in range(PC_CNT):
        prev_i = i - 1
        next_i = (i + 1) % PC_CNT
        _pc_ring[i].set_prev_pc(_pc_ring[prev_i])
        _pc_ring[i].set_next_pc(_pc_ring[next_i])


def get_pcs() -> Tuple[PC_app, ...]:
    return tuple(_pc_ring)


async def do_phy_ticks():
    while True:
        for pc in _pc_ring:
            pc.do_phy_tick()
        await asyncio.sleep(0)


async def do_app_ticks():
    while True:
        for pc in _pc_ring:
            await pc.do_app_tick()
            await asyncio.sleep(0)


def start_ticks():
    global _phy_ticks_task, _app_ticks_task
    if _phy_ticks_task is not None or _app_ticks_task is not None:
        raise RuntimeError("ticks are already running")
    _phy_ticks_task = asyncio.create_task(do_phy_ticks())
    _app_ticks_task = asyncio.create_task(do_app_ticks())


def stop_ticks():
    global _phy_ticks_task, _app_ticks_task
    if _phy_ticks_task is None or _app_ticks_task is None:
        raise RuntimeError("ticks are not running")
    _phy_ticks_task.cancel()
    _phy_ticks_task = None
    _app_ticks_task.cancel()
    _app_ticks_task = None

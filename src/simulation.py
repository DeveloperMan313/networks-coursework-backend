import asyncio
from asyncio.tasks import Task
from typing import List, Never, Tuple

from src.application import PC_app
from src.physical import BYTE_ERROR_PROB

_pc_ring: List[PC_app] = []

_phy_ticks_task: Task[Never] | None = None
_app_ticks_task: Task[Never] | None = None


def start_network(pc_cnt: int, byte_error_prob=BYTE_ERROR_PROB):
    global _phy_ticks_task, _app_ticks_task

    if _pc_ring:
        raise RuntimeError("network already initialized")

    for i in range(pc_cnt):
        _pc_ring.append(PC_app(i + 1, byte_error_prob))

    for i in range(pc_cnt):
        prev_i = i - 1
        next_i = (i + 1) % pc_cnt
        _pc_ring[i].set_prev_pc(_pc_ring[prev_i])
        _pc_ring[i].set_next_pc(_pc_ring[next_i])

    _phy_ticks_task = asyncio.create_task(do_phy_ticks())
    _app_ticks_task = asyncio.create_task(do_app_ticks())


def stop_network():
    global _phy_ticks_task, _app_ticks_task

    if not _pc_ring or _phy_ticks_task is None or _app_ticks_task is None:
        raise RuntimeError("network not initialized")

    _phy_ticks_task.cancel()
    _app_ticks_task.cancel()

    _pc_ring.clear()


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

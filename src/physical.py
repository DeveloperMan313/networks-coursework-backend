from enum import Enum, auto
from queue import Queue
from random import randint
from typing import Dict, List, Literal, Type, Union

from src.loggers import phy_logger

PinName = Literal["DCD", "RXD", "TXD", "DTR", "RTS", "CTS"]

_DTE_DTE_pin_connections: Dict[PinName, PinName] = {
    "DTR": "DCD",
    "DCD": "DTR",
    "TXD": "RXD",
    "RXD": "TXD",
    "RTS": "CTS",
    "CTS": "RTS",
}

TPB = 32  # Ticks Per Baud

TIMER_MAX_ERROR = 1

PC_CNT = 3

_pc_ring: List["PC_phy"] = []


class PC_phy:
    def __init__(self, name: str):
        self.name = name
        self._in_port = Port_phy(name + " in port")
        self._out_port = Port_phy(name + " out port")

    def connect_in_port(self, pc: "PC_phy"):
        self._in_port.connect(pc._out_port)

    def connect_out_port(self, pc: "PC_phy"):
        self._out_port.connect(pc._in_port)

    def disconnect_in_port(self):
        self._in_port.disconnect()

    def disconnect_out_port(self):
        self._out_port.disconnect()

    def do_tick(self):
        self._in_port.do_tick()
        self._out_port.do_tick()


# port states physical layer
class PS_phy(Enum):
    INACTIVE = auto()
    STANDBY = auto()
    TX_RTS = auto()
    TX_AWAIT_CTS = auto()
    TX_START_BIT = auto()
    TX_BYTE = auto()
    RX_CTS = auto()
    RX_AWAIT_RXD = auto()
    RX_SYNC = auto()
    RX_BYTE = auto()


class Port_phy:
    def __init__(self, name: str):
        self.name = name
        self.__pins: Dict[PinName, bool] = {
            "DCD": False,
            "RXD": False,
            "TXD": False,
            "DTR": False,
            "RTS": False,
            "CTS": False,
        }
        self.__connected_port: Union[Port_phy, None] = None
        self.__state = PS_phy.INACTIVE
        self.__timer: int = 0
        self.__send_buffer: Queue[int] = Queue()
        self.__receive_buffer: Queue[int] = Queue()
        self.__current_byte: int = 0
        self.__current_bit_mask: int = 1

    def connect(self, port: "Port_phy"):
        if self.__connected_port:
            raise RuntimeError("already connected to port")
        if port.__connected_port:
            raise RuntimeError("other port already connected to port")
        if port == self:
            raise RuntimeError("cannot connect to self")

        self.__connected_port = port
        port.__connected_port = self

        self.__set_pin("DTR", True)
        port.__set_pin("DTR", True)

        for pin in ("TXD", "RTS"):
            self.__set_pin(pin, self.__pins[pin])

    def disconnect(self):
        if not self.__connected_port:
            raise RuntimeError("not connected to port")

        self.__connected_port.__set_pin("DTR", False)
        self.__set_pin("DTR", False)

        self.__connected_port.__connected_port = None
        self.__connected_port = None

        for pin in ("TXD", "RTS"):
            self.__set_pin(pin, self.__pins[pin])

    def do_tick(self):
        if self.__timer == 0:
            self.__change_state()
            return

        self.__timer -= 1

    def _enqueue_send_byte(self, byte: int):
        if not 0 <= byte <= 255:
            raise ValueError("invalid byte")

        self.__send_buffer.put(byte)

    def _get_received_byte(self) -> int:
        return self.__receive_buffer.get(block=False)

    def _get_pin(self, pin: PinName) -> bool:  # must be accessible from tests
        if self.__connected_port:
            active = (
                self.__pins[pin]
                or self.__connected_port.__pins[_DTE_DTE_pin_connections[pin]]
            )
        else:
            active = self.__pins[pin]
        self.__log_debug(f"read pin {pin} as {active}")
        return active

    def __set_pin(self, pin: PinName, active: bool):
        self.__pins[pin] = active
        self.__log_debug(f"set pin {pin} to {active}")

    def __change_state(self):
        self.__timer = TPB + randint(-TIMER_MAX_ERROR, TIMER_MAX_ERROR)

        if not self._get_pin("DCD"):
            self.__set_state(PS_phy.INACTIVE)
            return

        match self.__state:
            case PS_phy.INACTIVE:
                if self._get_pin("DCD"):
                    self.__set_state(PS_phy.STANDBY)
            case PS_phy.STANDBY:
                if not self.__send_buffer.empty():
                    self.__current_byte = self.__send_buffer.get()
                    self.__set_pin("TXD", True)
                    self.__set_pin("RTS", True)
                    self.__set_state(PS_phy.TX_RTS)
                    return
                if self._get_pin("CTS"):
                    self.__set_pin("RTS", True)
                    self.__set_state(PS_phy.RX_CTS)
            case PS_phy.TX_RTS:
                self.__set_state(PS_phy.TX_AWAIT_CTS)
            case PS_phy.TX_AWAIT_CTS:
                if not self._get_pin("CTS"):
                    return
                self.__set_pin("TXD", False)
                self.__set_state(PS_phy.TX_START_BIT)
            case PS_phy.TX_START_BIT:
                self.__set_state(PS_phy.TX_BYTE)
            case PS_phy.TX_BYTE:
                if self.__current_bit_mask == 256:
                    self.__set_pin("RTS", False)
                    self.__set_state(PS_phy.STANDBY)
                    self.__log_debug(f"sent byte {self.__current_byte:08b}")
                    return
                self.__set_pin(
                    "TXD", bool(self.__current_byte & self.__current_bit_mask)
                )
                self.__current_bit_mask <<= 1
            case PS_phy.RX_CTS:
                self.__set_state(PS_phy.RX_AWAIT_RXD)
                self.__timer = 1  # high precision override
            case PS_phy.RX_AWAIT_RXD:
                if self._get_pin("RXD"):
                    self.__timer = 1  # high precision override
                    return
                self.__set_state(PS_phy.RX_SYNC)
            case PS_phy.RX_SYNC:
                self.__current_byte = 0
                self.__current_bit_mask = 1
                self.__timer += TPB // 2
                self.__set_state(PS_phy.RX_BYTE)
            case PS_phy.RX_BYTE:
                if self.__current_bit_mask == 256:
                    self.__receive_buffer.put(self.__current_byte)
                    self.__set_pin("RTS", False)
                    self.__set_state(PS_phy.STANDBY)
                    self.__log_debug(f"received byte {self.__current_byte:08b}")
                    return
                self.__current_byte += (
                    int(self._get_pin("RXD")) * self.__current_bit_mask
                )
                self.__current_bit_mask <<= 1

    def __set_state(self, state: PS_phy):
        self.__state = state
        self.__log_debug(f"changed state to {state}")

    def __log_debug(self, msg: object):
        phy_logger.debug("%s: %s", self.name, msg)


def init_network(PC: Type[PC_phy]):
    for i in range(PC_CNT):
        _pc_ring.append(PC(f"PC{i}"))

    for i in range(PC_CNT):
        prev_i = i - 1
        next_i = (i + 1) % PC_CNT
        _pc_ring[i].connect_in_port(_pc_ring[prev_i])
        _pc_ring[i].connect_out_port(_pc_ring[next_i])


def do_tick():
    for pc in _pc_ring:
        pc.do_tick()

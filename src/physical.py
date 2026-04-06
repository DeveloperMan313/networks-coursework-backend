from enum import Enum, auto
from queue import Queue
from random import randint
from typing import Dict, Literal, Union

from src.loggers import phy_logger

PinName = Literal["DCD", "RXD", "TXD", "DTR", "RTS", "CTS"]

DTE_DTE_pin_connections: Dict[PinName, PinName] = {
    "DTR": "DCD",
    "DCD": "DTR",
    "TXD": "RXD",
    "RXD": "TXD",
    "RTS": "CTS",
    "CTS": "RTS",
}

TPB = 32  # Ticks Per Baud

TIMER_MAX_ERROR = 1


class PC:
    def __init__(self, name: str):
        self.name = name
        self.__in_port = Port(name + " in port")
        self.__out_port = Port(name + " out port")


class PortState(Enum):
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


class Port:
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
        self.__connected_port: Union[Port, None] = None
        self.__state = PortState.INACTIVE
        self.__timer: int = 0
        self.__send_buffer: Queue[int] = Queue()
        self.__receive_buffer: Queue[int] = Queue()
        self.__current_byte: int = 0
        self.__current_bit_mask: int = 1

    def connect(self, port: "Port"):
        if self.__connected_port:
            raise RuntimeError("already connected to port")
        if port.__connected_port:
            raise RuntimeError("other port already connected to port")
        if port == self:
            raise RuntimeError("cannot connect to self")

        self.__connected_port = port
        port.__connected_port = self

        self.set_pin("DTR", True)
        port.set_pin("DTR", True)

        for pin in ("TXD", "RTS"):
            self.set_pin(pin, self.__pins[pin])

    def disconnect(self):
        if not self.__connected_port:
            raise RuntimeError("not connected to port")

        self.__connected_port.set_pin("DTR", False)
        self.set_pin("DTR", False)

        self.__connected_port.__connected_port = None
        self.__connected_port = None

        for pin in ("TXD", "RTS"):
            self.set_pin(pin, self.__pins[pin])

    def set_pin(self, pin: PinName, active: bool):
        self.__pins[pin] = active
        self.__log_debug(f"set pin {pin} to {active}")

    def enqueue_send_byte(self, byte: int):
        if not 0 <= byte <= 255:
            raise ValueError("invalid byte")

        self.__send_buffer.put(byte)

    def get_received_byte(self) -> int:
        return self.__receive_buffer.get(block=False)

    def do_tick(self):
        if self.__timer == 0:
            self.__change_state()
            return

        self.__timer -= 1

    def _get_pin(self, pin: PinName) -> bool:  # must be accessible from tests
        if self.__connected_port:
            active = (
                self.__pins[pin]
                or self.__connected_port.__pins[DTE_DTE_pin_connections[pin]]
            )
        else:
            active = self.__pins[pin]
        self.__log_debug(f"read pin {pin} as {active}")
        return active

    def __change_state(self):
        self.__timer = TPB + randint(-TIMER_MAX_ERROR, TIMER_MAX_ERROR)

        if not self._get_pin("DCD"):
            self.__set_state(PortState.INACTIVE)
            return

        match self.__state:
            case PortState.INACTIVE:
                if self._get_pin("DCD"):
                    self.__set_state(PortState.STANDBY)
            case PortState.STANDBY:
                if not self.__send_buffer.empty():
                    self.__current_byte = self.__send_buffer.get()
                    self.set_pin("TXD", True)
                    self.set_pin("RTS", True)
                    self.__set_state(PortState.TX_RTS)
                    return
                if self._get_pin("CTS"):
                    self.set_pin("RTS", True)
                    self.__set_state(PortState.RX_CTS)
            case PortState.TX_RTS:
                self.__set_state(PortState.TX_AWAIT_CTS)
            case PortState.TX_AWAIT_CTS:
                if not self._get_pin("CTS"):
                    return
                self.set_pin("TXD", False)
                self.__set_state(PortState.TX_START_BIT)
            case PortState.TX_START_BIT:
                self.__set_state(PortState.TX_BYTE)
            case PortState.TX_BYTE:
                if self.__current_bit_mask == 256:
                    self.set_pin("RTS", False)
                    self.__set_state(PortState.STANDBY)
                    self.__log_debug(f"sent byte {self.__current_byte:08b}")
                    return
                self.set_pin("TXD", bool(self.__current_byte & self.__current_bit_mask))
                self.__current_bit_mask <<= 1
            case PortState.RX_CTS:
                self.__set_state(PortState.RX_AWAIT_RXD)
                self.__timer = 1  # high precision override
            case PortState.RX_AWAIT_RXD:
                if self._get_pin("RXD"):
                    self.__timer = 1  # high precision override
                    return
                self.__set_state(PortState.RX_SYNC)
            case PortState.RX_SYNC:
                self.__current_byte = 0
                self.__current_bit_mask = 1
                self.__timer += TPB // 2
                self.__set_state(PortState.RX_BYTE)
            case PortState.RX_BYTE:
                if self.__current_bit_mask == 256:
                    self.__receive_buffer.put(self.__current_byte)
                    self.set_pin("RTS", False)
                    self.__set_state(PortState.STANDBY)
                    self.__log_debug(f"received byte {self.__current_byte:08b}")
                    return
                self.__current_byte += (
                    int(self._get_pin("RXD")) * self.__current_bit_mask
                )
                self.__current_bit_mask <<= 1

    def __set_state(self, state: PortState):
        self.__state = state
        self.__log_debug(f"changed state to {state}")

    def __log_debug(self, msg: object):
        phy_logger.debug("%s: %s", self.name, msg)

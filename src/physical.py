from enum import Enum, auto
from random import randint
from typing import Dict, Literal, Union

PinName = Literal["DCD", "RXD", "TXD", "DTR", "RTS", "CTS"]

DTE_DTE_pin_connections: Dict[PinName, PinName] = {
    "DTR": "DCD",
    "TXD": "RXD",
    "RTS": "CTS",
}

TPB = 16  # Ticks Per Baud

TIMER_MAX_ERROR = 3


class PC:
    def __init__(self):
        self.__in_port = Port()
        self.__out_port = Port()


class PortState(Enum):
    INACTIVE = auto()
    STANDBY = auto()
    TX_RTS = auto()
    TX_AWAIT_CTS = auto()
    TX_START_BIT = auto()
    TX_BYTE = auto()
    TX_STOP_BIT = auto()
    TX_END = auto()
    RX_AWAIT_RTS = auto()
    RX_CTS = auto()
    RX_AWAIT_RXD = auto()
    RX_SYNC = auto()
    RX_BYTE = auto()
    RX_END = auto()


class Port:
    def __init__(self):
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
        # TODO send/receive byte buffers

    def connect(self, port: "Port"):
        if self.__connected_port:
            raise RuntimeError("already connected to port")

        self.__connected_port = port

    def disconnect(self):
        if not self.__connected_port:
            raise RuntimeError("not connected to port")

        self.__connected_port = None

    def set_pin(self, pin: PinName, active: bool):
        self.__pins[pin] = active
        if not self.__connected_port:
            return

        other_pin = self.__connected_port.__pins[DTE_DTE_pin_connections[pin]]
        other_pin |= active

    def __change_state(self):
        self.__timer = TPB + randint(-TIMER_MAX_ERROR, TIMER_MAX_ERROR)

        if not (self.__connected_port and self.__pins["DCD"]):
            self.__state = PortState.INACTIVE
            return

        match self.__state:
            case PortState.INACTIVE:
                if self.__connected_port and self.__pins["DCD"]:
                    self.__state = PortState.STANDBY
            case _:  # TODO all states
                pass

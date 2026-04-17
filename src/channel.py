from enum import Enum, auto
from queue import Queue
from typing import Literal

from src.physical import PC_phy, Port_phy

T_MULT = 16  # cha tick multiplier relative to phy

_TIMEOUT = 3  # timeout in cha ticks


class PC_cha(PC_phy):
    def __init__(self, name: str):
        self.name = name
        self._in_port = Port_cha(name + " in port")
        self._out_port = Port_cha(name + " out port")


# port states channel layer
class PS_cha(Enum):
    INACTIVE = auto()
    STANDBY = auto()
    RX_AWAIT_REPEAT = auto()
    TX_UPLINK_AWAIT_ACK = auto()
    TX_DOWNLINK_AWAIT_ACK = auto()
    TX_LINKACTIVE_AWAIT_ACK = auto()
    TX_MAILSTART_AWAIT_ACK = auto()
    TX_MAILDATA_AWAIT_ACK = auto()
    TX_MAILEND_AWAIT_ACK = auto()
    RX_MAIL_AWAIT_FRAME_HEAD = auto()
    RX_MAILDATA_AWAIT_DATA = auto()


# port frame heads
class PFrameH(Enum):
    ACK = auto()
    NACK = auto()
    UPLINK = auto()
    DOWNLINK = auto()
    LINKACTIVE = auto()
    MAILSTART = auto()
    MAILDATA = auto()
    MAILEND = auto()


class Frame:
    _head: PFrameH
    _data: int | None

    def __init__(self, head: PFrameH, data: int | None = None):
        if head == PFrameH.MAILDATA and data is None:
            raise ValueError("MAILDATA frame should have data")
        if data and not 0 <= data <= 255:
            raise ValueError("invalid data")
        self._head = head
        self._data = data

    @property
    def head(self) -> PFrameH:
        return self._head

    @property
    def data(self) -> int | None:
        return self._data


class MsgTX(Frame):
    def __init__(
        self,
        head: Literal[
            PFrameH.UPLINK, PFrameH.DOWNLINK, PFrameH.LINKACTIVE, PFrameH.MAILDATA
        ],
        data: int | None = None,
    ):
        super().__init__(head, data)


class MsgRX(Frame):
    def __init__(
        self,
        head: Literal[
            PFrameH.UPLINK, PFrameH.DOWNLINK, PFrameH.LINKACTIVE, PFrameH.MAILDATA
        ],
        data: int,
    ):
        super().__init__(head, data)
        if head != PFrameH.MAILDATA and data != 1 and data != 0:
            raise ValueError(
                f"{head.name} message should have data 1 (success) or 0 (fail)"
            )


class Port_cha(Port_phy):
    def __init__(self, name: str):
        super().__init__(name)
        self.__state = PS_cha.INACTIVE
        self.__timer: int = 0
        self.__send_buffer: Queue[MsgTX] = Queue()
        self.__receive_buffer: Queue[MsgRX] = Queue()

    def enqueue_send_msg(self, msg: MsgTX):
        self.__send_buffer.put(msg)

    def get_received_msg(self) -> MsgRX:
        return self.__receive_buffer.get(block=False)

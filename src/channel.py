from enum import Enum, auto

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


class Port_cha(Port_phy):
    def __init__(self, name: str):
        super().__init__(name)

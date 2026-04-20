from enum import Enum, auto
from math import floor, log2
from queue import Queue
from random import randint
from typing import List, Literal, Tuple, cast

from src.loggers import cha_logger
from src.physical import TIMER_MAX_ERROR, TPB, PC_phy, Port_phy

T_MULT = 16  # cha tick multiplier relative to phy

_TIMEOUT = 5  # timeout in cha ticks


class PC_cha(PC_phy):
    def __init__(self, name: str):
        self.name = name
        self._in_port = Port_cha(name + " in port")
        self._out_port = Port_cha(name + " out port")


# port states channel layer
class PS_cha(Enum):
    INACTIVE = auto()
    STANDBY = auto()
    TX_UPLINK_AWAIT_ACK = auto()
    TX_DOWNLINK_AWAIT_ACK = auto()
    TX_LINKACTIVE_AWAIT_ACK = auto()
    TX_DATASTART_AWAIT_ACK = auto()
    TX_DATA_SEND_HEAD_OR_END = auto()
    TX_DATA_HEAD_AWAIT_ACK = auto()
    TX_DATA_DATA_AWAIT_ACK = auto()
    TX_DATAEND_AWAIT_ACK = auto()
    RX_DATA_AWAIT_HEAD_OR_END = auto()
    RX_DATA_AWAIT_DATA = auto()


# port frame heads
class PFrameH(Enum):
    ACK = auto()
    NACK = auto()
    UPLINK = auto()
    DOWNLINK = auto()
    LINKACTIVE = auto()
    DATASTART = auto()
    DATA = auto()
    DATAEND = auto()


# allowed heads for messages from/to app layer
AppMsgHead = Literal[PFrameH.UPLINK, PFrameH.DOWNLINK, PFrameH.LINKACTIVE, PFrameH.DATA]


class Frame:
    _head: PFrameH
    _data: int | None

    def __init__(self, head: PFrameH, data: int | None = None):
        if data and not 0 <= data <= 15:
            raise ValueError("invalid data")
        self._head = head
        self._data = data

    @property
    def head(self) -> PFrameH:
        return self._head

    @property
    def data(self) -> int | None:
        return self._data

    def __eq__(self, value: object, /) -> bool:
        if not isinstance(value, Frame):
            return False
        return self.head == value.head and self.data == value.data


class MsgTX(Frame):
    def __init__(
        self,
        head: AppMsgHead,
        data: int | None = None,
    ):
        super().__init__(head, data)


class MsgRX(Frame):
    def __init__(
        self,
        head: AppMsgHead,
        data: int,
    ):
        super().__init__(head, data)
        if head != PFrameH.DATA and data != 1 and data != 0:
            raise ValueError(
                f"{head.name} message should have data 1 (success) or 0 (fail)"
            )


class Port_cha(Port_phy):
    __GEN_POLY_7_4 = 0b1011
    __POLY_SHIFT = 7 - 4

    def __init__(self, name: str):
        super().__init__(name)
        self.__state = PS_cha.INACTIVE
        self.__timer: int = 0
        self.__ticks_waiting: int = 0
        self.__send_buffer: Queue[MsgTX] = Queue()
        self.__receive_buffer: Queue[MsgRX] = Queue()
        self.__send_str_buffer: Queue[str] = Queue()
        self.__receive_str_buffer: Queue[str] = Queue()
        self.__current_str_chunks: List[int] = []
        self.__current_data_chunk: int = 0
        self.__is_sending_data: bool = False

    def enqueue_send_msg(self, msg: MsgTX):
        self.__send_buffer.put(msg)

    def enqueue_send_str(self, string: str):
        self.__send_str_buffer.put(string)

    def get_received_msg(self) -> MsgRX:
        return self.__receive_buffer.get(block=False)

    def get_received_str(self) -> str:
        return self.__receive_str_buffer.get(block=False)

    def do_tick(self):
        super().do_tick()

        if self.__timer == 0:
            self.__change_state()
            return

        self.__timer -= 1

    def __change_state(self):
        self.__timer = (TPB + randint(-TIMER_MAX_ERROR, TIMER_MAX_ERROR)) * T_MULT

        if self.__state != PS_cha.INACTIVE and self.__ticks_waiting == _TIMEOUT:
            self.__ticks_waiting = 0
            self.__log_debug("response timeout reached")
            self.__set_state(PS_cha.STANDBY)
            return

        if (
            self.__state in (PS_cha.INACTIVE, PS_cha.STANDBY)
        ) and self.__is_sending_data:
            fail_msg = MsgRX(PFrameH.DATA, 0)
            self.__put_to_receive_buffer(fail_msg)
            self.__is_sending_data = False

        match self.__state:
            case PS_cha.INACTIVE:
                frame = self.__try_receive_1chunk_frame()
                if frame:
                    if not self.__frame_head_must_be_of(frame.head, (PFrameH.UPLINK,)):
                        return
                    self.__send_1chunk_frame(PFrameH.ACK)
                    self.__set_state(PS_cha.STANDBY)
                    return
                if not self.__send_buffer.empty():
                    msg = self.__get_from_send_buffer()
                    if not self.__frame_head_must_be_of(msg.head, (PFrameH.UPLINK,)):
                        fail_msg = MsgRX(cast(AppMsgHead, msg.head), 0)
                        self.__put_to_receive_buffer(fail_msg)
                        return
                    self.__send_1chunk_frame(PFrameH.UPLINK)
                    self.__set_state(PS_cha.TX_UPLINK_AWAIT_ACK)
            case PS_cha.STANDBY:
                frame = self.__try_receive_1chunk_frame()
                if frame:
                    if not self.__frame_head_must_be_of(
                        frame.head,
                        (PFrameH.DOWNLINK, PFrameH.LINKACTIVE, PFrameH.DATASTART),
                    ):
                        return
                    match frame.head:
                        case PFrameH.DOWNLINK:
                            self.__send_1chunk_frame(PFrameH.ACK)
                            self.__set_state(PS_cha.INACTIVE)
                        case PFrameH.LINKACTIVE:
                            self.__send_1chunk_frame(PFrameH.ACK)
                        case PFrameH.DATASTART:
                            self.__current_str_chunks.clear()
                            self.__send_1chunk_frame(PFrameH.ACK)
                            self.__set_state(PS_cha.RX_DATA_AWAIT_HEAD_OR_END)
                    return
                if not self.__send_buffer.empty():
                    msg = self.__get_from_send_buffer()
                    if not self.__frame_head_must_be_of(
                        msg.head, (PFrameH.DOWNLINK, PFrameH.LINKACTIVE)
                    ):
                        fail_msg = MsgRX(cast(AppMsgHead, msg.head), 0)
                        self.__put_to_receive_buffer(fail_msg)
                        return
                    match msg.head:
                        case PFrameH.DOWNLINK:
                            self.__send_1chunk_frame(PFrameH.DOWNLINK)
                            self.__set_state(PS_cha.TX_DOWNLINK_AWAIT_ACK)
                        case PFrameH.LINKACTIVE:
                            self.__send_1chunk_frame(PFrameH.LINKACTIVE)
                            self.__set_state(PS_cha.TX_LINKACTIVE_AWAIT_ACK)
                    return
                if not self.__send_str_buffer.empty():
                    string = self.__send_str_buffer.get()
                    self.__log_debug(f"got string from send buffer:\n{string}")
                    str_bytes = string.encode("utf-8")
                    self.__current_str_chunks.clear()
                    for byte in str_bytes:
                        lower_chunk = byte & 0b1111
                        upper_chunk = byte >> 4
                        self.__current_str_chunks.append(lower_chunk)
                        self.__current_str_chunks.append(upper_chunk)
                    self.__is_sending_data = True
                    self.__send_1chunk_frame(PFrameH.DATASTART)
                    self.__set_state(PS_cha.TX_DATASTART_AWAIT_ACK)
            case PS_cha.TX_UPLINK_AWAIT_ACK:
                self.__ticks_waiting += 1
                frame = self.__try_receive_1chunk_frame()
                if not frame or not self.__frame_head_must_be_of(
                    frame.head, (PFrameH.ACK,)
                ):
                    return
                success_msg = MsgRX(PFrameH.UPLINK, 1)
                self.__put_to_receive_buffer(success_msg)
                self.__set_state(PS_cha.STANDBY)
            case PS_cha.TX_DOWNLINK_AWAIT_ACK:
                self.__ticks_waiting += 1
                frame = self.__try_receive_1chunk_frame()
                if not frame or not self.__frame_head_must_be_of(
                    frame.head, (PFrameH.ACK,)
                ):
                    return
                success_msg = MsgRX(PFrameH.DOWNLINK, 1)
                self.__put_to_receive_buffer(success_msg)
                self.__set_state(PS_cha.INACTIVE)
            case PS_cha.TX_LINKACTIVE_AWAIT_ACK:
                self.__ticks_waiting += 1
                frame = self.__try_receive_1chunk_frame()
                if not frame or not self.__frame_head_must_be_of(
                    frame.head, (PFrameH.ACK,)
                ):
                    return
                success_msg = MsgRX(PFrameH.LINKACTIVE, 1)
                self.__put_to_receive_buffer(success_msg)
                self.__set_state(PS_cha.STANDBY)
            case PS_cha.TX_DATASTART_AWAIT_ACK:
                self.__ticks_waiting += 1
                frame = self.__try_receive_1chunk_frame()
                if not frame or not self.__frame_head_must_be_of(
                    frame.head, (PFrameH.ACK,)
                ):
                    return
                self.__set_state(PS_cha.TX_DATA_SEND_HEAD_OR_END)
            case PS_cha.TX_DATA_SEND_HEAD_OR_END:
                if not self.__current_str_chunks:
                    self.__send_1chunk_frame(PFrameH.DATAEND)
                    self.__set_state(PS_cha.TX_DATAEND_AWAIT_ACK)
                    return
                self.__current_data_chunk = self.__current_str_chunks.pop(0)
                self.__send_1chunk_frame(PFrameH.DATA)
                self.__set_state(PS_cha.TX_DATA_HEAD_AWAIT_ACK)
            case PS_cha.TX_DATA_HEAD_AWAIT_ACK:
                self.__ticks_waiting += 1
                frame = self.__try_receive_1chunk_frame()
                if not frame or not self.__frame_head_must_be_of(
                    frame.head, (PFrameH.ACK,)
                ):
                    return
                self.__send_chunk(self.__current_data_chunk)
                self.__set_state(PS_cha.TX_DATA_DATA_AWAIT_ACK)
            case PS_cha.TX_DATA_DATA_AWAIT_ACK:
                self.__ticks_waiting += 1
                frame = self.__try_receive_1chunk_frame()
                if not frame or not self.__frame_head_must_be_of(
                    frame.head, (PFrameH.ACK,)
                ):
                    return
                self.__set_state(PS_cha.TX_DATA_SEND_HEAD_OR_END)
            case PS_cha.TX_DATAEND_AWAIT_ACK:
                self.__ticks_waiting += 1
                frame = self.__try_receive_1chunk_frame()
                if not frame or not self.__frame_head_must_be_of(
                    frame.head, (PFrameH.ACK,)
                ):
                    return
                self.__is_sending_data = False
                success_msg = MsgRX(PFrameH.DATA, 1)
                self.__put_to_receive_buffer(success_msg)
                self.__is_sending_data = False
                self.__set_state(PS_cha.STANDBY)
            case PS_cha.RX_DATA_AWAIT_HEAD_OR_END:
                self.__ticks_waiting += 1
                frame = self.__try_receive_1chunk_frame()
                if not frame or not self.__frame_head_must_be_of(
                    frame.head, (PFrameH.DATA, PFrameH.DATAEND)
                ):
                    return
                match frame.head:
                    case PFrameH.DATA:
                        self.__send_1chunk_frame(PFrameH.ACK)
                        self.__set_state(PS_cha.RX_DATA_AWAIT_DATA)
                    case PFrameH.DATAEND:
                        if len(self.__current_str_chunks) % 2 != 0:
                            raise RuntimeError("received chunk count must be even")
                        str_bytes = bytearray()
                        for i in range(len(self.__current_str_chunks) // 2):
                            lower_chunk = self.__current_str_chunks[i * 2]
                            upper_chunk = self.__current_str_chunks[i * 2 + 1]
                            str_bytes.append((upper_chunk << 4) + lower_chunk)
                        string = str_bytes.decode("utf-8")
                        self.__log_debug(f"put string into receive buffer:\n{string}")
                        self.__receive_str_buffer.put(string)
                        self.__send_1chunk_frame(PFrameH.ACK)
                        self.__set_state(PS_cha.STANDBY)
            case PS_cha.RX_DATA_AWAIT_DATA:
                self.__ticks_waiting += 1
                chunk = self.__try_receive_chunk()
                if chunk is None:
                    return
                self.__current_str_chunks.append(chunk)
                self.__send_1chunk_frame(PFrameH.ACK)
                self.__set_state(PS_cha.RX_DATA_AWAIT_HEAD_OR_END)

    def __send_chunk(self, raw_chunk: int):
        if not 0 <= raw_chunk <= 15:
            raise ValueError("invalid chunk")

        raw_chunk_shifted = raw_chunk << Port_cha.__POLY_SHIFT
        encoded_chunk = (raw_chunk_shifted) + Port_cha.divide_polynoms_remainder(
            raw_chunk_shifted, Port_cha.__GEN_POLY_7_4
        )
        self.__log_debug(
            f"sending chunk {raw_chunk:>04b} encoded as {encoded_chunk:>07b}"
        )
        self._enqueue_send_byte(encoded_chunk)

    def __send_1chunk_frame(self, head: PFrameH):
        self.__log_debug(f"sending 1-chunk frame {head.name}")
        self.__send_chunk(head.value)

    def __try_receive_chunk(self) -> int | None:
        if not self._has_received_bytes():
            return None

        encoded_chunk = self._get_received_byte()
        syndrome = Port_cha.divide_polynoms_remainder(
            encoded_chunk, Port_cha.__GEN_POLY_7_4
        )
        raw_chunk = encoded_chunk >> Port_cha.__POLY_SHIFT
        if syndrome == 0:
            self.__log_debug(
                f"received valid encoded chunk {encoded_chunk:>07b}, decoded as {raw_chunk:>04b}"
            )
            return raw_chunk

        self.__log_debug(
            f"received invalid encoded chunk {encoded_chunk:>07b}, sending NACK"
        )
        self.__send_1chunk_frame(PFrameH.NACK)
        return None

    def __try_receive_1chunk_frame(self) -> Frame | None:
        chunk = self.__try_receive_chunk()
        if chunk is None:
            return None
        frame_head = PFrameH(chunk)
        self.__log_debug(f"received 1-chunk frame {frame_head}")
        return Frame(frame_head)  # assuming it isn't data chunk of DATA-frame

    def __get_from_send_buffer(self) -> MsgTX:
        msg = self.__send_buffer.get()
        if msg.data is not None:
            self.__log_debug(
                f"got msg from send buffer: head {msg.head}, data {msg.data:>04b}"
            )
        if msg.data is None:
            self.__log_debug(f"got msg from send buffer: head {msg.head}")
        return msg

    def __put_to_receive_buffer(self, msg: MsgRX):
        self.__receive_buffer.put(msg)
        if msg.data is not None:
            self.__log_debug(
                f"put msg to receive buffer: head {msg.head}, data {msg.data:>04b}"
            )
        if msg.data is None:
            self.__log_debug(f"put msg to receive buffer: head {msg.head}")

    def __frame_head_must_be_of(
        self, head: PFrameH, acceptable: Tuple[PFrameH, ...]
    ) -> bool:
        if head not in acceptable:
            self.__log_debug(
                f"incorrect frame {head}, must be one of ({', '.join(map(str, acceptable))})"
            )
            return False
        return True

    @staticmethod
    def divide_polynoms_remainder(dividend: int, divisor: int) -> int:
        if dividend == 0:
            return 0

        len_dividend = floor(log2(dividend)) + 1
        len_divisor = floor(log2(divisor)) + 1

        for i in range(len_dividend - len_divisor + 1):
            if dividend & (1 << (len_dividend - 1 - i)):
                dividend ^= divisor << (len_dividend - len_divisor - i)

        remainder = dividend & ((1 << (len_divisor - 1)) - 1)

        return remainder

    def __set_state(self, state: PS_cha):
        self.__state = state
        self.__log_debug(f"changed state to {state}")
        self.__ticks_waiting = 0

    def __log_debug(self, msg: object):
        cha_logger.debug("%s: %s", self._name, msg)

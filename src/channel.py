from enum import Enum, auto
from math import floor, log2
from queue import Queue
from random import randint
from typing import List, Literal, Tuple, cast

from src.loggers import cha_logger
from src.physical import TIMER_MAX_ERROR, TPB, Port_phy

T_MULT = 16  # cha tick multiplier relative to phy

_TIMEOUT_TICKS = 10  # timeout in cha ticks

_TIMEOUT_NACKS = 5  # max consecutive NACKs


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
    NACK = 0
    ACK = 1
    UPLINK = 2
    DOWNLINK = 3
    LINKACTIVE = 4
    DATASTART = 5
    DATA = 6
    DATAEND = 7


MsgReq = Literal[PFrameH.UPLINK, PFrameH.DOWNLINK, PFrameH.LINKACTIVE]


class MsgRes:
    def __init__(self, req: MsgReq | Literal[PFrameH.DATA], success: bool):
        self.req = req
        self.success = success

    def __eq__(self, value: object, /) -> bool:
        if not isinstance(value, MsgRes):
            return False
        return self.req == value.req and self.success == value.success


class Port_cha(Port_phy):
    __GEN_POLY_7_4 = 0b1011
    __POLY_SHIFT = 7 - 4

    def __init__(self, name: str):
        super().__init__(name)
        self.__state = PS_cha.INACTIVE
        self.__timer: int = 0
        self.__ticks_waiting: int = 0
        self.__consecutive_nacks: int = 0
        self.__send_buffer: Queue[MsgReq] = Queue()
        self.__receive_buffer: Queue[MsgRes] = Queue()
        self.__send_str_buffer: Queue[str] = Queue()
        self.__receive_str_buffer: Queue[str] = Queue()
        self.__current_str_chunks: List[int] = []
        self.__last_sent_chunk: int | None = None
        self.__current_data_chunk: int = 0
        self.__is_sending_data: bool = False

    def get_received_str(self) -> str:
        return self.__receive_str_buffer.get(block=False)

    def has_received_str(self) -> bool:
        return not self.__receive_str_buffer.empty()

    def do_tick(self):
        super().do_tick()

        if self.__timer == 0:
            self.__change_state()
            return

        self.__timer -= 1

    def _enqueue_request(self, req: MsgReq):
        self.__send_buffer.put(req)

    def _enqueue_send_str(self, string: str):
        self.__send_str_buffer.put(string)

    def _get_response(self) -> MsgRes:
        return self.__receive_buffer.get(block=False)

    def _has_response(self) -> bool:
        return not self.__receive_buffer.empty()

    def __change_state(self):
        self.__timer = (TPB + randint(-TIMER_MAX_ERROR, TIMER_MAX_ERROR)) * T_MULT

        if self.__ticks_waiting == _TIMEOUT_TICKS:
            self.__ticks_waiting = 0
            self.__log_debug("response timeout reached")
            self.__set_state(PS_cha.STANDBY)
            return

        if (
            self.__state in (PS_cha.INACTIVE, PS_cha.STANDBY)
        ) and self.__is_sending_data:
            fail_res = MsgRes(PFrameH.DATA, False)
            self.__put_to_receive_buffer(fail_res)
            self.__is_sending_data = False

        match self.__state:
            case PS_cha.INACTIVE:
                head = self.__try_receive_1chunk_frame()
                if head:
                    if not self.__frame_head_must_be_of(head, (PFrameH.UPLINK,)):
                        self.__send_1chunk_frame(PFrameH.NACK)
                        return
                    self.__send_1chunk_frame(PFrameH.ACK)
                    self.__set_state(PS_cha.STANDBY)
                    return
                if not self.__send_buffer.empty():
                    req = self.__get_from_send_buffer()
                    if not self.__frame_head_must_be_of(req, (PFrameH.UPLINK,)):
                        fail_res = MsgRes(cast(MsgReq, req), False)
                        self.__put_to_receive_buffer(fail_res)
                        return
                    self.__send_1chunk_frame(PFrameH.UPLINK)
                    self.__set_state(PS_cha.TX_UPLINK_AWAIT_ACK)
            case PS_cha.STANDBY:
                head = self.__try_receive_1chunk_frame()
                if head:
                    if not self.__frame_head_must_be_of(
                        head,
                        (PFrameH.DOWNLINK, PFrameH.LINKACTIVE, PFrameH.DATASTART),
                    ):
                        self.__send_1chunk_frame(PFrameH.NACK)
                        return
                    match head:
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
                    req = self.__get_from_send_buffer()
                    if not self.__frame_head_must_be_of(
                        req, (PFrameH.DOWNLINK, PFrameH.LINKACTIVE)
                    ):
                        fail_res = MsgRes(cast(MsgReq, req), False)
                        self.__put_to_receive_buffer(fail_res)
                        return
                    match req:
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
                        lower_chunk = byte & 0b00000111
                        middle_chunk = (byte & 0b00111000) >> 3
                        upper_chunk = (byte & 0b11000000) >> 6
                        self.__current_str_chunks.append(lower_chunk)
                        self.__current_str_chunks.append(middle_chunk)
                        self.__current_str_chunks.append(upper_chunk)
                    self.__is_sending_data = True
                    self.__send_1chunk_frame(PFrameH.DATASTART)
                    self.__set_state(PS_cha.TX_DATASTART_AWAIT_ACK)
            case PS_cha.TX_UPLINK_AWAIT_ACK:
                self.__ticks_waiting += 1
                head = self.__try_receive_1chunk_frame()
                if not head:
                    return
                if not self.__frame_head_must_be_of(head, (PFrameH.ACK,)):
                    self.__send_1chunk_frame(PFrameH.NACK)
                    return
                success_res = MsgRes(PFrameH.UPLINK, True)
                self.__put_to_receive_buffer(success_res)
                self.__set_state(PS_cha.STANDBY)
            case PS_cha.TX_DOWNLINK_AWAIT_ACK:
                self.__ticks_waiting += 1
                head = self.__try_receive_1chunk_frame()
                if not head:
                    return
                if not self.__frame_head_must_be_of(head, (PFrameH.ACK,)):
                    self.__send_1chunk_frame(PFrameH.NACK)
                    return
                success_res = MsgRes(PFrameH.DOWNLINK, True)
                self.__put_to_receive_buffer(success_res)
                self.__set_state(PS_cha.INACTIVE)
            case PS_cha.TX_LINKACTIVE_AWAIT_ACK:
                self.__ticks_waiting += 1
                head = self.__try_receive_1chunk_frame()
                if not head:
                    return
                if not self.__frame_head_must_be_of(head, (PFrameH.ACK,)):
                    self.__send_1chunk_frame(PFrameH.NACK)
                    return
                success_res = MsgRes(PFrameH.LINKACTIVE, True)
                self.__put_to_receive_buffer(success_res)
                self.__set_state(PS_cha.STANDBY)
            case PS_cha.TX_DATASTART_AWAIT_ACK:
                self.__ticks_waiting += 1
                head = self.__try_receive_1chunk_frame()
                if not head:
                    return
                if not self.__frame_head_must_be_of(head, (PFrameH.ACK,)):
                    self.__send_1chunk_frame(PFrameH.NACK)
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
                head = self.__try_receive_1chunk_frame()
                if not head:
                    return
                if not self.__frame_head_must_be_of(head, (PFrameH.ACK,)):
                    self.__send_1chunk_frame(PFrameH.NACK)
                    return
                # set MSB to 1 for data chunk
                self.__send_chunk(0b1000 ^ self.__current_data_chunk)
                self.__set_state(PS_cha.TX_DATA_DATA_AWAIT_ACK)
            case PS_cha.TX_DATA_DATA_AWAIT_ACK:
                self.__ticks_waiting += 1
                head = self.__try_receive_1chunk_frame()
                if not head:
                    return
                if not self.__frame_head_must_be_of(head, (PFrameH.ACK,)):
                    self.__send_1chunk_frame(PFrameH.NACK)
                    return
                self.__set_state(PS_cha.TX_DATA_SEND_HEAD_OR_END)
            case PS_cha.TX_DATAEND_AWAIT_ACK:
                self.__ticks_waiting += 1
                head = self.__try_receive_1chunk_frame()
                if not head:
                    return
                if not self.__frame_head_must_be_of(head, (PFrameH.ACK,)):
                    self.__send_1chunk_frame(PFrameH.NACK)
                    return
                self.__is_sending_data = False
                success_res = MsgRes(PFrameH.DATA, True)
                self.__put_to_receive_buffer(success_res)
                self.__is_sending_data = False
                self.__set_state(PS_cha.STANDBY)
            case PS_cha.RX_DATA_AWAIT_HEAD_OR_END:
                self.__ticks_waiting += 1
                head = self.__try_receive_1chunk_frame()
                if not head:
                    return
                if not self.__frame_head_must_be_of(
                    head, (PFrameH.DATA, PFrameH.DATAEND)
                ):
                    self.__send_1chunk_frame(PFrameH.NACK)
                    return
                match head:
                    case PFrameH.DATA:
                        self.__send_1chunk_frame(PFrameH.ACK)
                        self.__set_state(PS_cha.RX_DATA_AWAIT_DATA)
                    case PFrameH.DATAEND:
                        if len(self.__current_str_chunks) % 3 != 0:
                            raise RuntimeError(
                                "received chunk count must be multiple of 3"
                            )
                        str_bytes = bytearray()
                        for i in range(len(self.__current_str_chunks) // 3):
                            lower_chunk = self.__current_str_chunks[i * 3]
                            middle_chunk = self.__current_str_chunks[i * 3 + 1]
                            upper_chunk = self.__current_str_chunks[i * 3 + 2]
                            str_bytes.append(
                                (upper_chunk << 6) + (middle_chunk << 3) + lower_chunk
                            )
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
                # set MSB 1 back to 0 for data chunk
                self.__current_str_chunks.append(0b1000 ^ chunk)
                self.__send_1chunk_frame(PFrameH.ACK)
                self.__set_state(PS_cha.RX_DATA_AWAIT_HEAD_OR_END)

    # chunk consists of 4 bits, of which MSB is 0 for HEAD and 1 for DATA, 3 other bits are payload
    # e.g. 0000 is NACK head, 1101 is 101 data
    # this method presumes raw_chunk is following these rules
    def __send_chunk(self, raw_chunk: int):
        if not 0 <= raw_chunk <= 15:
            raise ValueError("invalid chunk")

        if raw_chunk != PFrameH.NACK.value:
            self.__last_sent_chunk = raw_chunk

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

        self.__ticks_waiting = 0

        encoded_chunk = self._get_received_byte()
        syndrome = Port_cha.divide_polynoms_remainder(
            encoded_chunk, Port_cha.__GEN_POLY_7_4
        )
        raw_chunk = encoded_chunk >> Port_cha.__POLY_SHIFT
        if syndrome == 0:
            self.__log_debug(
                f"received valid encoded chunk {encoded_chunk:>07b}, decoded as {raw_chunk:>04b}"
            )
            # NACK can be sent in response to any frame
            # MSB of data chunks is 1, so we know 0000 is definitely NACK
            if raw_chunk == PFrameH.NACK.value:
                self.__consecutive_nacks += 1
                if self.__consecutive_nacks == _TIMEOUT_NACKS:
                    self.__log_debug("too many consecutive NACKs")
                    self.__set_state(PS_cha.STANDBY)
                    return None
                if self.__state == PS_cha.INACTIVE:
                    self.__log_debug("received NACK, ignore because port is INACTIVE")
                    return None
                self.__log_debug("received NACK, sending last sent chunk")
                self.__send_chunk(
                    self.__last_sent_chunk
                    if self.__last_sent_chunk
                    else PFrameH.NACK.value
                )
                return None

            self.__consecutive_nacks = 0
            self.__last_sent_chunk = None
            return raw_chunk

        self.__log_debug(
            f"received invalid encoded chunk {encoded_chunk:>07b}, sending NACK"
        )
        self.__send_1chunk_frame(PFrameH.NACK)
        return None

    def __try_receive_1chunk_frame(self) -> PFrameH | None:
        chunk = self.__try_receive_chunk()
        if chunk is None:
            return None
        try:
            head = PFrameH(chunk)
            self.__log_debug(f"received 1-chunk frame {head}")
            return head  # assuming it isn't data chunk of DATA-frame
        except ValueError:
            self.__log_debug(f"received invalid chunk frame {chunk:>04b}, sending NACK")
            self.__send_1chunk_frame(PFrameH.NACK)
            return None

    def __get_from_send_buffer(self) -> MsgReq:
        req = self.__send_buffer.get()
        self.__log_debug(f"got request from send buffer: {req}")
        return req

    def __put_to_receive_buffer(self, res: MsgRes):
        self.__receive_buffer.put(res)
        self.__log_debug(
            f"put response to receive buffer: {res} {'' if res.success else 'un'}successful"
        )

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

    def __log_debug(self, msg: object):
        cha_logger.debug("%s: %s", self._name, msg)

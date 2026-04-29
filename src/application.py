import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, List, Literal, Type, cast

from src.channel import MsgReq, PFrameH, Port_cha
from src.loggers import app_logger
from src.physical import PC_phy

MailAddress = str
EmailID = int


@dataclass
class AppMsgPayload:
    source_address: MailAddress

    def to_json(self) -> str:
        data = asdict(self)
        return json.dumps(data)

    @classmethod
    def from_json(cls, json_str: str) -> "AppMsgPayload":
        data = json.loads(json_str)
        return cls(**data)


@dataclass
class EmailConnect(AppMsgPayload):
    pass


@dataclass
class EmailConnectAck(AppMsgPayload):
    pass


@dataclass
class EmailDisconnect(AppMsgPayload):
    pass


@dataclass
class Email(AppMsgPayload):
    id: EmailID
    From: MailAddress
    to: MailAddress
    date: datetime
    in_reply_to: EmailID
    resent_from: MailAddress | None
    resent_to: MailAddress | None
    resent_date: datetime | None

    def to_json(self) -> str:
        data = asdict(self)
        data["date"] = datetime.now(timezone.utc).isoformat()
        return json.dumps(data)

    @classmethod
    def from_json(cls, json_str: str) -> "Email":
        data = json.loads(json_str)
        data["date"] = datetime.fromisoformat(data["date"])
        return cls(**data)


@dataclass
class EmailAck(AppMsgPayload):
    id: EmailID


class PC_app(PC_phy):
    __CLASS_TO_TYPE_STR: Dict[Type[AppMsgPayload], str] = {
        EmailConnect: "EMAIL_CONNECT",
        EmailConnectAck: "EMAIL_CONNECT_ACK",
        EmailDisconnect: "EMAIL_DISCONNECT",
        Email: "EMAIL",
        EmailAck: "EMAIL_ACK",
    }
    __TYPE_STR_TO_CLASS: Dict[str, Type[AppMsgPayload]] = {
        v: k for k, v in __CLASS_TO_TYPE_STR.items()
    }

    def __init__(self, name: str):
        super().__init__(name)
        self.__name = name
        self._in_port = Port_app(name + ", in port")
        self._out_port = Port_app(name + ", out port")
        self.__address: MailAddress | None = None
        self.__network_addresses: List[MailAddress] = []
        self.__received_emails: List[Email] = []

    @property
    def name(self) -> str:
        return self.__name

    @property
    def network_addresses(self) -> List[MailAddress]:
        return self.__network_addresses

    @property
    def received_emails(self) -> List[Email]:
        return self.__received_emails

    async def channel_uplink(self, port: Literal["in_port", "out_port"]):
        if port == "in_port":
            await self._in_port.channel_uplink()
        if port == "out_port":
            await self._out_port.channel_uplink()

    async def channel_downlink(self, port: Literal["in_port", "out_port"]):
        if port == "in_port":
            await self._in_port.channel_downlink()
        if port == "out_port":
            await self._out_port.channel_downlink()

    async def channel_active(self, port: Literal["in_port", "out_port"]) -> bool:
        if port == "in_port":
            return await self._in_port.channel_active()
        if port == "out_port":
            return await self._out_port.channel_active()

    async def email_connect(self, address: MailAddress):
        if self.__address is not None:
            raise RuntimeError("already connected to network")
        await self.__send_message_payload(EmailConnect(source_address=address))
        self.__address = address

    def send_email(self, email: Email):
        pass

    async def do_app_tick(self):
        await self.__try_receive_handle_message()

    async def __try_receive_handle_message(self):
        if not self._in_port.has_received_str():
            return

        string = self._in_port.get_received_str()
        type, payload = string.split("\n", 1)
        msg_class = self.__TYPE_STR_TO_CLASS[type]
        payload = msg_class.from_json(payload)

        # drop message that was sent by this PC
        if payload.source_address == self.__address:
            return

        match payload:
            case EmailConnect():
                await self.__handle_received_email_connect(payload)
            case EmailConnectAck():
                await self.__handle_received_email_connect_ack(payload)
            case _:
                pass  # TODO handle all classes

    async def __handle_received_email_connect(self, email_connect: EmailConnect):
        if email_connect.source_address not in self.__network_addresses:
            self.__network_addresses.append(email_connect.source_address)
        await self.__send_message_payload(email_connect)
        if self.__address is not None:
            await self.__send_message_payload(
                EmailConnectAck(source_address=self.__address)
            )

    async def __handle_received_email_connect_ack(
        self, email_connect_ack: EmailConnectAck
    ):
        if email_connect_ack.source_address not in self.__network_addresses:
            self.__network_addresses.append(email_connect_ack.source_address)

    async def __send_message_payload(self, payload: AppMsgPayload):
        string = f"{self.__CLASS_TO_TYPE_STR[type(payload)]}\n{payload.to_json()}"
        await self._out_port.send_str(string)


class Port_app(Port_cha):
    def __init__(self, name: str):
        super().__init__(name)
        self.__response_callbacks: List[Callable[[bool], None]] = []

    async def channel_uplink(self):
        await self.__send_message("UPLINK")

    async def channel_downlink(self):
        await self.__send_message("DOWNLINK")

    async def channel_active(self) -> bool:
        try:
            await self.__send_message("LINKACTIVE")
            return True
        except RuntimeError:
            return False

    async def send_str(self, string: str):
        self.__log_debug(f"sending string:\n{string}")
        self._enqueue_send_str(string)
        future: asyncio.Future[bool] = asyncio.Future()

        def callback(success):
            future.set_result(success)

        self.__response_callbacks.append(callback)
        success = await future
        if not success:
            raise RuntimeError("sending string failed")
        self.__log_debug("successfully sent string")

    def get_received_str(self) -> str:
        string = super().get_received_str()
        self.__log_debug(f"received string:\n{string}")
        return string

    def do_tick(self):
        super().do_tick()
        self.__try_receive_handle_response()

    async def __send_message(self, msg: Literal["UPLINK", "DOWNLINK", "LINKACTIVE"]):
        self.__log_debug(f"sending message {msg}")
        self._enqueue_request(cast(MsgReq, PFrameH[msg]))
        future: asyncio.Future[bool] = asyncio.Future()

        def callback(success):
            future.set_result(success)

        self.__response_callbacks.append(callback)
        success = await future
        if not success:
            raise RuntimeError("sending message failed")
        self.__log_debug(f"successfully sent {msg}")

    def __try_receive_handle_response(self):
        if not self._has_response():
            return
        response = self._get_response()
        callback = self.__response_callbacks.pop(0)
        callback(response.success)

    def __log_debug(self, msg: object):
        app_logger.debug("%s: %s", self._name, msg)

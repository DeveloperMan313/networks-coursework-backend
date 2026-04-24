import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Callable, List, Literal, cast

from src.channel import MsgReq, PFrameH, Port_cha
from src.physical import PC_phy

MailAddress = int | Literal["*"]
EmailID = int


@dataclass
class Email:
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
    def from_json(cls, json_str: str):
        data = json.loads(json_str)
        data["date"] = datetime.fromisoformat(data["date"])
        return cls(**data)


class PC_app(PC_phy):
    def __init__(self, name: str):
        super().__init__(name)
        self.__received_emails: List[Email] = []

    def send_email(self, email: Email):
        pass

    def get_received_emails(self) -> List[Email]:
        return self.__received_emails


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
        self.enqueue_send_str(string)
        future: asyncio.Future[bool] = asyncio.Future()

        def callback(success):
            future.set_result(success)

        self.__response_callbacks.append(callback)
        success = await future
        if not success:
            raise RuntimeError("sending string failed")

    def do_tick(self):
        super().do_tick()
        self.__try_receive_handle_response()

    async def __send_message(self, msg: Literal["UPLINK", "DOWNLINK", "LINKACTIVE"]):
        self.enqueue_request(cast(MsgReq, PFrameH[msg]))
        future: asyncio.Future[bool] = asyncio.Future()

        def callback(success):
            future.set_result(success)

        self.__response_callbacks.append(callback)
        success = await future
        if not success:
            raise RuntimeError("sending message failed")

    def __try_receive_handle_response(self):
        if not self.has_response():
            return
        response = self.get_response()
        callback = self.__response_callbacks.pop(0)
        callback(response.success)

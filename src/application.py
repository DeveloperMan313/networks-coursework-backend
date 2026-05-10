import asyncio
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, List, Literal, Type, cast

from src.data_link import MsgReq, PFrameH, Port_dtl
from src.entities.app_events import (
    AppEvent,
    EmailGotAck,
    EmailReceived,
    EmailSent,
    PCConnected,
    PCDisconnected,
    PortStateChanged,
)
from src.entities.email_protocol import (
    AppMsgPayload,
    Email,
    EmailAck,
    EmailAddress,
    EmailBody,
    EmailConnect,
    EmailConnectAck,
    EmailDisconnect,
    EmailID,
    EmailSubject,
)
from src.loggers import app_logger
from src.physical import BYTE_ERROR_PROB, PC_phy, PCAddress

_MAX_SEND_MSG_RETRIES = 8


@dataclass
class PortStates:
    in_phy_up: bool = False
    in_dtl_up: bool = False
    out_phy_up: bool = False
    out_dtl_up: bool = False


class PC_app(PC_phy):
    __TYPE_STR_TO_CLASS: Dict[str, Type[AppMsgPayload]] = {
        c.__name__: c
        for c in [EmailConnect, EmailConnectAck, EmailDisconnect, Email, EmailAck]
    }

    def __init__(self, address: PCAddress, byte_error_prob=BYTE_ERROR_PROB):
        super().__init__(address, byte_error_prob)
        self.__name = f"PC{address}"
        self._in_port = Port_app(f"{self.__name}, in port", byte_error_prob)
        self._out_port = Port_app(f"{self.__name}, out port", byte_error_prob)
        self.__address: PCAddress = address
        self.__email_address: EmailAddress | None = None
        self.__network_addresses: List[EmailAddress] = []
        self.__sent_emails: List[Email] = []
        self.__received_emails: List[Email] = []
        self.__port_states = PortStates()
        self.__events: asyncio.Queue[AppEvent] = asyncio.Queue()

    @property
    def name(self) -> str:
        return self.__name

    @property
    def address(self) -> PCAddress:
        return self.__address

    @property
    def email_address(self) -> EmailAddress | None:
        return self.__email_address

    @property
    def network_addresses(self) -> List[EmailAddress]:
        return self.__network_addresses

    @property
    def sent_emails(self) -> List[Email]:
        return self.__sent_emails

    @property
    def received_emails(self) -> List[Email]:
        return self.__received_emails

    async def get_event(self) -> AppEvent:
        return await self.__events.get()

    async def data_link_uplink(self, port: Literal["in_port", "out_port"]):
        if port == "in_port":
            await self._in_port.data_link_uplink()
        if port == "out_port":
            await self._out_port.data_link_uplink()

    async def data_link_downlink(self, port: Literal["in_port", "out_port"]):
        if port == "in_port":
            await self._in_port.data_link_downlink()
        if port == "out_port":
            await self._out_port.data_link_downlink()

    async def data_link_active(self, port: Literal["in_port", "out_port"]) -> bool:
        if port == "in_port":
            return await self._in_port.data_link_active()
        if port == "out_port":
            return await self._out_port.data_link_active()

    async def email_connect(self, address: EmailAddress):
        if self.__email_address is not None:
            raise RuntimeError("already connected to network")
        await self.__send_message_payload(
            EmailConnect(source_address=self.__address, address=address)
        )
        self.__email_address = address

    async def email_disconnect(self):
        if self.__email_address is None:
            raise RuntimeError("not connected to network")
        await self.__send_message_payload(
            EmailDisconnect(source_address=self.__address, address=self.__email_address)
        )
        self.__email_address = None
        for address in self.__network_addresses:
            await self.__events.put(PCDisconnected(address=address))
        self.__network_addresses.clear()

    async def send_email(
        self,
        to: EmailAddress,
        subject: EmailSubject,
        body: EmailBody,
        in_reply_to: EmailID | None = None,
    ):
        if in_reply_to is not None and not any(
            e.id == in_reply_to for e in self.__sent_emails
        ):
            raise ValueError("in_reply_to does not match any of sent emails' IDs")
        if to != "*" and to not in self.__network_addresses:
            raise ValueError("to is not in network_addresses")
        email = self.__get_blank_email()
        email.to = to
        email.subject = subject
        email.body = body
        email.in_reply_to = in_reply_to
        email.should_receive = [to] if to != "*" else self.__network_addresses.copy()
        await self.__send_message_payload(email)
        self.__sent_emails.append(email)
        await self.__events.put(EmailSent(email=email))

    async def resend_email(self, id: EmailID, to: EmailAddress):
        all_emails = self.__sent_emails + self.__received_emails
        if not any(e.id == id for e in all_emails):
            raise ValueError("id does not match any of emails' IDs")
        if to != "*" and to not in self.__network_addresses:
            raise ValueError("to is not in network_addresses")
        if self.__email_address is None:
            raise RuntimeError("cannot send email while disconnected")
        now = datetime.now(timezone.utc)
        email = deepcopy(next(filter(lambda e: e.id == id, all_emails)))
        email.source_address = self.__address
        email.id = int(now.timestamp() * 1000)
        email.resent_from = self.__email_address
        email.resent_to = to
        email.resent_date = now
        email.should_receive = [to] if to != "*" else self.__network_addresses.copy()
        email.have_received.clear()
        await self.__send_message_payload(email)
        self.__sent_emails.append(email)
        await self.__events.put(EmailSent(email=email))

    async def do_app_tick(self):
        await self.__update_port_states()
        try:
            await self.__try_receive_handle_message()
        except Exception:
            pass

    async def __update_port_states(self):
        curr_states = self.__port_states
        new_states = PortStates(
            in_phy_up=self._in_port.phy_is_up(),
            in_dtl_up=self._in_port.dtl_is_up(),
            out_phy_up=self._out_port.phy_is_up(),
            out_dtl_up=self._out_port.dtl_is_up(),
        )

        if curr_states.in_phy_up != new_states.in_phy_up:
            await self.__events.put(
                PortStateChanged(port="in", layer="phy", is_up=new_states.in_phy_up)
            )
        if curr_states.in_dtl_up != new_states.in_dtl_up:
            await self.__events.put(
                PortStateChanged(port="in", layer="dtl", is_up=new_states.in_dtl_up)
            )
        if curr_states.out_phy_up != new_states.out_phy_up:
            await self.__events.put(
                PortStateChanged(port="out", layer="phy", is_up=new_states.out_phy_up)
            )
        if curr_states.out_dtl_up != new_states.out_dtl_up:
            await self.__events.put(
                PortStateChanged(port="out", layer="dtl", is_up=new_states.out_dtl_up)
            )

        self.__port_states = new_states

    def __get_blank_email(self) -> Email:
        if self.__email_address is None:
            raise RuntimeError("cannot send email while disconnected")
        now = datetime.now(timezone.utc)
        email = Email(
            source_address=self.__address,
            id=int(now.timestamp() * 1000),
            From=self.__email_address,
            to="*",
            date=now,
            in_reply_to=None,
            resent_from=None,
            resent_to=None,
            resent_date=None,
            subject=" ",
            body="",
            should_receive=[],
            have_received=[],
        )
        return email

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

        # only forward message if this PC is not connected
        if self.__email_address is None:
            await self.__send_message_payload(payload)
            return

        match payload:
            case EmailConnect():
                if payload.address not in self.__network_addresses:
                    await self.__events.put(PCConnected(address=payload.address))
                    self.__network_addresses.append(payload.address)
                await self.__send_message_payload(payload)
                await self.__send_message_payload(
                    EmailConnectAck(
                        source_address=self.__address, address=self.__email_address
                    )
                )

            case EmailConnectAck():
                if payload.address not in self.__network_addresses:
                    await self.__events.put(PCConnected(address=payload.address))
                    self.__network_addresses.append(payload.address)
                await self.__send_message_payload(payload)

            case EmailDisconnect():
                if payload.address in self.__network_addresses:
                    await self.__events.put(PCDisconnected(address=payload.address))
                    self.__network_addresses.remove(payload.address)
                await self.__send_message_payload(payload)

            case Email():
                to = payload.resent_to if payload.resent_to else payload.to
                if to == self.__email_address:
                    await self.__events.put(EmailReceived(email=payload))
                    self.__received_emails.append(payload)
                    await self.__send_message_payload(
                        EmailAck(
                            source_address=self.__address,
                            id=payload.id,
                            address=self.__email_address,
                        )
                    )
                    return
                if to == "*":
                    await self.__events.put(EmailReceived(email=payload))
                    self.__received_emails.append(payload)
                    await self.__send_message_payload(
                        EmailAck(
                            source_address=self.__address,
                            id=payload.id,
                            address=self.__email_address,
                        )
                    )
                await self.__send_message_payload(payload)

            case EmailAck():
                email = next(
                    filter(lambda e: e.id == payload.id, self.__sent_emails), None
                )
                if email:
                    await self.__events.put(
                        EmailGotAck(id=payload.id, address=payload.address)
                    )
                    if payload.address not in email.should_receive:
                        email.should_receive.append(payload.address)
                    email.have_received.append(payload.address)
                    return
                await self.__send_message_payload(payload)

    async def __send_message_payload(self, payload: AppMsgPayload):
        string = f"{type(payload).__name__}\n{payload.to_json()}"
        await self._out_port.send_str(string)


class Port_app(Port_dtl):
    def __init__(self, name: str, byte_error_prob=BYTE_ERROR_PROB):
        super().__init__(name, byte_error_prob)
        self.__response_callbacks: List[Callable[[bool], None]] = []

    async def data_link_uplink(self):
        await self.__send_message("UPLINK")

    async def data_link_downlink(self):
        await self.__send_message("DOWNLINK")

    async def data_link_active(self) -> bool:
        try:
            await self.__send_message("LINKACTIVE")
            return True
        except RuntimeError:
            return False

    async def send_str(self, string: str):
        retries = 0

        while True:
            if retries == _MAX_SEND_MSG_RETRIES:
                raise RuntimeError("sending string failed")

            self.__log_debug(f"sending string:\n{string}")
            self._enqueue_send_str(string)
            future: asyncio.Future[bool] = asyncio.Future()

            def callback(success):
                future.set_result(success)

            self.__response_callbacks.append(callback)
            success = await future
            if not success:
                retries += 1
                continue
            self.__log_debug("successfully sent string")
            return

    def get_received_str(self) -> str:
        string = super().get_received_str()
        self.__log_debug(f"received string:\n{string}")
        return string

    def do_tick(self):
        super().do_tick()
        self.__try_receive_handle_response()

    async def __send_message(self, msg: Literal["UPLINK", "DOWNLINK", "LINKACTIVE"]):
        retries = 0

        while True:
            if retries == _MAX_SEND_MSG_RETRIES:
                raise RuntimeError("sending message failed")
            self.__log_debug(f"sending message {msg}")
            self._enqueue_request(cast(MsgReq, PFrameH[msg]))
            future: asyncio.Future[bool] = asyncio.Future()

            def callback(success):
                future.set_result(success)

            self.__response_callbacks.append(callback)
            success = await future
            if not success:
                retries += 1
                continue
            self.__log_debug(f"successfully sent {msg}")
            return

    def __try_receive_handle_response(self):
        if not self._has_response():
            return
        response = self._get_response()
        callback = self.__response_callbacks.pop(0)
        callback(response.success)

    def __log_debug(self, msg: object):
        app_logger.debug("%s: %s", self._name, msg)

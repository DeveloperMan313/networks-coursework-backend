import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from typing import Callable, Dict, List, Literal, Type, cast

from src.data_link import MsgReq, PFrameH, Port_dtl
from src.db import db_get_pc_emails, db_save_pc_email
from src.entities.api import EmailBody, EmailSubject
from src.entities.app_messages import (
    AppMsg,
    Email,
    EmailAck,
    EmailAddress,
    EmailConnect,
    EmailConnectAck,
    EmailDisconnect,
    EmailID,
    EmailMsg,
)
from src.loggers import app_logger
from src.physical import BYTE_ERROR_PROB, PC_phy, PCAddress

_MAX_SEND_MSG_RETRIES = 8


class PC_app(PC_phy):
    __TYPE_STR_TO_CLASS: Dict[str, Type[AppMsg]] = {
        c.__name__: c
        for c in [EmailConnect, EmailConnectAck, EmailDisconnect, EmailMsg, EmailAck]
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

    def get_port_states(self) -> Dict[str, bool]:
        return {
            "in_phy_up": self._in_port.phy_is_up(),
            "in_dtl_up": self._in_port.dtl_is_up(),
            "out_phy_up": self._out_port.phy_is_up(),
            "out_dtl_up": self._out_port.dtl_is_up(),
        }

    async def data_link_uplink(self, port: Literal["in", "out"]):
        if port == "in":
            await self._in_port.data_link_uplink()
        if port == "out":
            await self._out_port.data_link_uplink()

    async def data_link_downlink(self, port: Literal["in", "out"]):
        if port == "in":
            await self._in_port.data_link_downlink()
        if port == "out":
            await self._out_port.data_link_downlink()

    async def data_link_active(self, port: Literal["in", "out"]) -> bool:
        if port == "in":
            return await self._in_port.data_link_active()
        if port == "out":
            return await self._out_port.data_link_active()

    async def email_connect(self, address: EmailAddress):
        if self.__email_address is not None:
            raise RuntimeError("already connected to network")
        await self.__send_message(
            EmailConnect(source_address=self.__address, address=address)
        )
        self.__email_address = address
        emails = db_get_pc_emails(self.__address, self.__email_address)
        for email in emails:
            author = email.resent_sender if email.resent_sender else email.sender
            if author == self.__email_address:
                self.__sent_emails.append(email)
            else:
                self.__received_emails.append(email)

    async def email_disconnect(self):
        if self.__email_address is None:
            raise RuntimeError("not connected to network")
        await self.__send_message(
            EmailDisconnect(source_address=self.__address, address=self.__email_address)
        )
        self.__email_address = None
        self.__network_addresses.clear()

    async def send_email(
        self,
        to: EmailAddress,
        subject: EmailSubject,
        body: EmailBody,
        in_reply_to: EmailID | None = None,
    ):
        if self.__email_address is None:
            raise RuntimeError("cannot send email while disconnected")
        if in_reply_to is not None and not any(
            e.id == in_reply_to for e in self.__sent_emails
        ):
            raise ValueError("in_reply_to does not match any of sent emails' IDs")
        if to != "*" and to not in self.__network_addresses:
            raise ValueError("to is not in network_addresses")
        email = self.__get_blank_email()
        email.receiver = to
        email.subject = subject
        email.body = body
        email.in_reply_to = in_reply_to
        email.should_receive = [to] if to != "*" else self.__network_addresses.copy()
        await self.__send_message(
            EmailMsg(source_address=self.__address, **email.model_dump())
        )
        self.__sent_emails.append(email)
        db_save_pc_email(self.__address, self.__email_address, email)

    async def resend_email(self, id: EmailID, to: EmailAddress):
        if self.__email_address is None:
            raise RuntimeError("cannot send email while disconnected")
        all_emails = self.__sent_emails + self.__received_emails
        if not any(e.id == id for e in all_emails):
            raise ValueError("id does not match any of emails' IDs")
        if to != "*" and to not in self.__network_addresses:
            raise ValueError("to is not in network_addresses")
        now = datetime.now(timezone.utc)
        email = deepcopy(next(filter(lambda e: e.id == id, all_emails)))
        email.id = int(now.timestamp() * 1000)
        email.resent_sender = self.__email_address
        email.resent_receiver = to
        email.resent_date = now
        email.should_receive = [to] if to != "*" else self.__network_addresses.copy()
        email.have_received.clear()
        await self.__send_message(
            EmailMsg(source_address=self.__address, **email.model_dump())
        )
        self.__sent_emails.append(email)
        db_save_pc_email(self.__address, self.__email_address, email)

    async def do_app_tick(self):
        try:
            await self.__try_receive_handle_message()
        except Exception as e:
            print(e)

    def __get_blank_email(self) -> Email:
        if self.__email_address is None:
            raise RuntimeError("cannot send email while disconnected")
        now = datetime.now(timezone.utc)
        email = Email(
            id=int(now.timestamp() * 1000),
            sender=self.__email_address,
            receiver="*",
            date=now,
            in_reply_to=None,
            resent_sender=None,
            resent_receiver=None,
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
        type, msg = string.split("\n", 1)
        msg_class = self.__TYPE_STR_TO_CLASS[type]
        msg = msg_class.model_validate_json(msg)

        # drop message that was sent by this PC
        if msg.source_address == self.__address:
            return

        # only forward message if this PC is not connected
        if self.__email_address is None:
            await self.__send_message(msg)
            return

        match msg:
            case EmailConnect():
                if msg.address not in self.__network_addresses:
                    self.__network_addresses.append(msg.address)
                await self.__send_message(msg)
                await self.__send_message(
                    EmailConnectAck(
                        source_address=self.__address, address=self.__email_address
                    )
                )

            case EmailConnectAck():
                if msg.address not in self.__network_addresses:
                    self.__network_addresses.append(msg.address)
                await self.__send_message(msg)

            case EmailDisconnect():
                if msg.address in self.__network_addresses:
                    self.__network_addresses.remove(msg.address)
                await self.__send_message(msg)

            case EmailMsg():
                to = msg.resent_receiver if msg.resent_receiver else msg.receiver
                if to == self.__email_address:
                    self.__received_emails.append(msg)
                    db_save_pc_email(self.__address, self.__email_address, msg)
                    await self.__send_message(
                        EmailAck(
                            source_address=self.__address,
                            id=msg.id,
                            address=self.__email_address,
                        )
                    )
                    return
                if to == "*":
                    self.__received_emails.append(msg)
                    db_save_pc_email(self.__address, self.__email_address, msg)
                    await self.__send_message(
                        EmailAck(
                            source_address=self.__address,
                            id=msg.id,
                            address=self.__email_address,
                        )
                    )
                await self.__send_message(msg)

            case EmailAck():
                email = next(filter(lambda e: e.id == msg.id, self.__sent_emails), None)
                if email:
                    if msg.address not in email.should_receive:
                        email.should_receive.append(msg.address)
                    email.have_received.append(msg.address)
                    db_save_pc_email(self.__address, self.__email_address, email)
                    return
                await self.__send_message(msg)

    async def __send_message(self, msg: AppMsg):
        string = f"{type(msg).__name__}\n{msg.model_dump_json()}"
        await self._out_port.send_str(string)


class Port_app(Port_dtl):
    def __init__(self, name: str, byte_error_prob=BYTE_ERROR_PROB):
        super().__init__(name, byte_error_prob)
        self.__response_callbacks: List[Callable[[bool], None]] = []

    async def data_link_uplink(self):
        if self.dtl_is_up():
            raise RuntimeError("data link already up")
        await self.__send_message("UPLINK")

    async def data_link_downlink(self):
        if not self.dtl_is_up():
            raise RuntimeError("data link already down")
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

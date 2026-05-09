import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Annotated, List

from pydantic import AfterValidator

from src.physical import PCAddress

EmailID = int


def validate_email_address(value: str) -> str:
    l_min, l_max = 3, 30
    if value == "*":
        return value
    if not (l_min <= len(value) <= l_max):
        raise ValueError(f"length must be {l_min}–{l_max}")
    if not re.fullmatch(r"[\w.-]+", value):
        raise ValueError("only letters, digits, _, ., - allowed")
    return value


EmailAddress = Annotated[str, AfterValidator(validate_email_address)]


def validate_email_subject(value: str) -> str:
    l_min, l_max = 1, 80
    if not (l_min <= len(value) <= l_max):
        raise ValueError(f"length must be {l_min}–{l_max}")
    if not value.isprintable():
        raise ValueError("should not contain unprintable characters")
    return value


EmailSubject = Annotated[str, AfterValidator(validate_email_subject)]


def validate_email_body(value: str) -> str:
    l_min, l_max = 0, 1000
    if not (l_min <= len(value) <= l_max):
        raise ValueError(f"length must be {l_min}–{l_max}")
    return value


EmailBody = Annotated[str, AfterValidator(validate_email_body)]


@dataclass
class AppMsgPayload:
    source_address: PCAddress

    def to_json(self) -> str:
        data = asdict(self)
        return json.dumps(data)

    @classmethod
    def from_json(cls, json_str: str) -> "AppMsgPayload":
        data = json.loads(json_str)
        return cls(**data)


@dataclass
class EmailConnect(AppMsgPayload):
    address: EmailAddress


@dataclass
class EmailConnectAck(AppMsgPayload):
    address: EmailAddress


@dataclass
class EmailDisconnect(AppMsgPayload):
    address: EmailAddress


@dataclass
class Email(AppMsgPayload):
    id: EmailID
    From: EmailAddress
    to: EmailAddress
    date: datetime
    in_reply_to: EmailID | None
    resent_from: EmailAddress | None
    resent_to: EmailAddress | None
    resent_date: datetime | None
    subject: EmailSubject
    body: EmailBody
    should_receive: List[EmailAddress]  # not serialized
    have_received: List[EmailAddress]  # not serialized

    def to_json(self) -> str:
        data = asdict(self)
        data["date"] = datetime.now(timezone.utc).isoformat()
        data["from"] = data.pop("From")
        del data["should_receive"]
        del data["have_received"]
        return json.dumps(data)

    @classmethod
    def from_json(cls, json_str: str) -> "Email":
        data = json.loads(json_str)
        data["date"] = datetime.fromisoformat(data["date"])
        data["From"] = data.pop("from")
        data["should_receive"] = []
        data["have_received"] = []
        return cls(**data)


@dataclass
class EmailAck(AppMsgPayload):
    id: EmailID
    address: EmailAddress

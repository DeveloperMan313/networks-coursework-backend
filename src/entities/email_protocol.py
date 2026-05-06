import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from src.physical import PCAddress

EmailID = int


class EmailAddress(str):
    def __new__(cls, value: str):
        l_min = 3
        l_max = 30
        if value == "*":
            return super().__new__(cls, value)
        if not l_min <= len(value) <= l_max:
            raise ValueError(
                f"{cls.__name__} should be {l_min} to {l_max} characters long"
            )
        if not re.fullmatch(r"[\w.-]+", value):
            raise ValueError(
                f"{cls.__name__} should consist of only letters, digits and symbols _-."
            )
        return super().__new__(cls, value)


class EmailSubject(str):
    def __new__(cls, value: str):
        l_min = 1
        l_max = 80
        if not l_min <= len(value) <= l_max:
            raise ValueError(
                f"{cls.__name__} should be {l_min} to {l_max} characters long"
            )
        if not value.isprintable():
            raise ValueError(f"{cls.__name__} should be printable")
        return super().__new__(cls, value)


class EmailBody(str):
    def __new__(cls, value: str):
        l_min = 0
        l_max = 1000
        if not l_min <= len(value) <= l_max:
            raise ValueError(
                f"{cls.__name__} should be {l_min} to {l_max} characters long"
            )
        return super().__new__(cls, value)


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

    def to_json(self) -> str:
        data = asdict(self)
        data["date"] = datetime.now(timezone.utc).isoformat()
        data["from"] = data.pop("From")
        return json.dumps(data)

    @classmethod
    def from_json(cls, json_str: str) -> "Email":
        data = json.loads(json_str)
        data["date"] = datetime.fromisoformat(data["date"])
        data["From"] = data.pop("from")
        return cls(**data)


@dataclass
class EmailAck(AppMsgPayload):
    id: EmailID

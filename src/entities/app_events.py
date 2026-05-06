import json
from dataclasses import asdict, dataclass

from src.entities.email_protocol import Email, EmailAddress


@dataclass
class AppEvent:
    def to_json(self) -> str:
        data = {"type": self.__class__.__name__, "payload": asdict(self)}
        return json.dumps(data)


@dataclass
class PCConnected(AppEvent):
    address: EmailAddress


@dataclass
class PCDisconnected(AppEvent):
    address: EmailAddress


@dataclass
class EmailSent(AppEvent):
    email: Email


@dataclass
class EmailReceived(AppEvent):
    email: Email

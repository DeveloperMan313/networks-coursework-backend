import re
from datetime import datetime
from typing import List

from pydantic import AfterValidator, BaseModel
from typing_extensions import Annotated

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


class Email(BaseModel):
    id: EmailID
    sender: EmailAddress
    receiver: EmailAddress
    date: datetime
    in_reply_to: EmailID | None
    resent_sender: EmailAddress | None
    resent_receiver: EmailAddress | None
    resent_date: datetime | None
    subject: EmailSubject
    body: EmailBody
    should_receive: List[EmailAddress]
    have_received: List[EmailAddress]

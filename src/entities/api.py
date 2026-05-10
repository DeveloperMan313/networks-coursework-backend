from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Dict, List

from pydantic import AfterValidator, BaseModel, Field

from src.entities import email_protocol
from src.entities.email_protocol import EmailAddress, EmailBody, EmailID, EmailSubject
from src.physical import PCAddress
from src.simulation import get_pcs

# entities


def validate_pc_id(value: int) -> int:
    pcs_len = len(get_pcs())
    if not (1 <= value <= pcs_len):
        raise ValueError(f"must be 1–{pcs_len}")
    return value


PCId = Annotated[int, AfterValidator(validate_pc_id)]


class Email(BaseModel):
    id: EmailID
    From: EmailAddress = Field(alias="from")
    to: EmailAddress
    date: datetime
    in_reply_to: EmailID | None
    resent_from: EmailAddress | None
    resent_to: EmailAddress | None
    resent_date: datetime | None
    subject: EmailSubject
    body: EmailBody
    should_receive: List[EmailAddress]
    have_received: List[EmailAddress]

    @classmethod
    def from_dataclass(cls, email: email_protocol.Email) -> "Email":
        data = asdict(email)
        data["from"] = data.pop("From")
        return cls(**data)


# requests and responses


class GetPCsResponse(BaseModel):
    pcs: Dict[PCAddress, EmailAddress | None]


class RegisterPCRequest(BaseModel):
    address: EmailAddress


class GetPCPortStatesResponse(BaseModel):
    in_phy_up: bool
    in_dtl_up: bool
    out_phy_up: bool
    out_dtl_up: bool


class SetPCPortStateRequest(BaseModel):
    is_up: bool


class TestPCPortLinkActiveResponse(BaseModel):
    active: bool


class GetPCEmailsResponse(BaseModel):
    sent: List[Email]
    received: List[Email]


class SendPCEmailRequest(BaseModel):
    to: EmailAddress
    subject: EmailSubject
    body: EmailBody
    in_reply_to: EmailID | None = None


class ResendPCEmailRequest(BaseModel):
    to: EmailAddress

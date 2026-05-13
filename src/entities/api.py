from typing import Dict, List

from pydantic import BaseModel

from src.entities.email import Email, EmailAddress, EmailBody, EmailID, EmailSubject
from src.physical import PCAddress


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
    receiver: EmailAddress
    subject: EmailSubject
    body: EmailBody
    in_reply_to: EmailID | None = None


class ResendPCEmailRequest(BaseModel):
    receiver: EmailAddress

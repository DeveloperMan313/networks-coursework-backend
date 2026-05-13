from pydantic import BaseModel

from src.entities.email import Email, EmailAddress, EmailID
from src.physical import PCAddress


class AppMsg(BaseModel):
    source_address: PCAddress


class EmailConnect(AppMsg):
    address: EmailAddress


class EmailConnectAck(AppMsg):
    address: EmailAddress


class EmailDisconnect(AppMsg):
    address: EmailAddress


class EmailMsg(AppMsg, Email):
    pass


class EmailAck(AppMsg):
    id: EmailID
    address: EmailAddress

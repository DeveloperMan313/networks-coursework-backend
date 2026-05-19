from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import AfterValidator

from src import simulation
from src.entities.api import (
    Email,
    GetPCEmailsResponse,
    GetPCPortStatesResponse,
    GetPCResponse,
    GetPCsResponse,
    RegisterPCRequest,
    ResendPCEmailRequest,
    SendPCEmailRequest,
    SetPCPortStateRequest,
    TestPCPortLinkActiveResponse,
)
from src.entities.app_messages import EmailID

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def validate_pc_id(value: int) -> int:
    pcs_len = len(simulation.get_pcs())
    if not (1 <= value <= pcs_len):
        raise ValueError(f"must be 1–{pcs_len}")
    return value


PCId = Annotated[int, AfterValidator(validate_pc_id)]


async def validate_registered_pc_id(pc_id: PCId) -> PCId:
    pc = simulation.get_pcs()[pc_id - 1]
    if pc.email_address is None:
        raise HTTPException(status_code=409, detail="PC not registered")
    return pc_id


pcs_router = APIRouter(prefix="/pcs/{pc_id}")

registered_pcs_router = APIRouter(
    prefix="/pcs/{pc_id}",
    dependencies=[Depends(validate_registered_pc_id)],
)


@app.get(
    "/pcs",
    response_model=GetPCsResponse,
    description="Returned data does not represent current simulation state as seen from PCs. PCs data updates with delay relative to this data.",
    tags=["PCs"],
)
def get_pcs():
    pcs = simulation.get_pcs()
    return {"pcs": {pc.address: pc.email_address for pc in pcs}}


@pcs_router.put("/register", status_code=204, tags=["PCs"])
async def register_pc(pc_id: PCId, req: RegisterPCRequest):
    pcs = simulation.get_pcs()
    pc = pcs[pc_id - 1]

    if pc.email_address is not None:
        raise HTTPException(status_code=409, detail="PC already registered")
    if req.address in [pc.email_address for pc in pcs]:
        raise HTTPException(status_code=409, detail="Address already registered")

    try:
        await pc.email_connect(req.address)
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e))


@registered_pcs_router.get("", response_model=GetPCResponse, tags=["PCs"])
def get_pc(pc_id: PCId):
    pc = simulation.get_pcs()[pc_id - 1]
    return {"address": pc.email_address, "network_addresses": pc.network_addresses}


@registered_pcs_router.put("/unregister", status_code=204, tags=["PCs"])
async def unregister_pc(pc_id: PCId):
    pc = simulation.get_pcs()[pc_id - 1]
    try:
        await pc.email_disconnect()
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e))


@pcs_router.get("/ports", response_model=GetPCPortStatesResponse, tags=["Ports"])
def get_pc_port_states(pc_id: PCId):
    pc = simulation.get_pcs()[pc_id - 1]
    return pc.port_states


@pcs_router.put(
    "/ports/{port}/{layer}",
    status_code=204,
    description="Not idempotent, changing state to itself will cause error",
    tags=["Ports"],
)
async def set_pc_port_state(
    pc_id: PCId,
    port: Literal["in", "out"],
    layer: Literal["phy", "dtl"],
    req: SetPCPortStateRequest,
):
    pc = simulation.get_pcs()[pc_id - 1]
    try:
        match (layer, req.is_up):
            case ("phy", True):
                pc.connect_port(port)
            case ("phy", False):
                pc.disconnect_port(port)
            case ("dtl", True):
                await pc.data_link_uplink(port)
            case ("dtl", False):
                await pc.data_link_downlink(port)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@pcs_router.post(
    "/ports/{port}/test-link-active",
    response_model=TestPCPortLinkActiveResponse,
    description="Side effect: might downlink port if it was physically disconnected",
    tags=["Ports"],
)
async def test_pc_port_link_active(pc_id: PCId, port: Literal["in", "out"]):
    pc = simulation.get_pcs()[pc_id - 1]
    return {"active": await pc.data_link_active(port)}


@registered_pcs_router.get(
    "/emails",
    response_model=GetPCEmailsResponse,
    description="newer_than is not inclusive",
    tags=["Emails"],
)
def get_pc_emails(
    pc_id: PCId,
    newer_than: datetime = Query(datetime.fromtimestamp(0, tz=timezone.utc)),
):
    pc = simulation.get_pcs()[pc_id - 1]
    sent = [
        Email.model_validate(e)
        for e in pc.sent_emails
        if (e.resent_date if e.resent_date else e.date) > newer_than
    ]
    received = [
        Email.model_validate(e)
        for e in pc.received_emails
        if (e.resent_date if e.resent_date else e.date) > newer_than
    ]
    return {"sent": sent, "received": received}


@registered_pcs_router.post("/emails", status_code=201, tags=["Emails"])
async def send_pc_email(pc_id: PCId, req: SendPCEmailRequest):
    pc = simulation.get_pcs()[pc_id - 1]
    try:
        await pc.send_email(req.receiver, req.subject, req.body, req.in_reply_to)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@registered_pcs_router.post("/emails/{email_id}", status_code=201, tags=["Emails"])
async def resend_pc_email(pc_id: PCId, email_id: EmailID, req: ResendPCEmailRequest):
    pc = simulation.get_pcs()[pc_id - 1]
    try:
        await pc.resend_email(email_id, req.receiver)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


app.include_router(pcs_router)
app.include_router(registered_pcs_router)

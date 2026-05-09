from fastapi import APIRouter, Depends, FastAPI, HTTPException

from src import simulation
from src.entities.api import (
    Email,
    GetPCEmailsResponse,
    GetPCsResponse,
    PCId,
    RegisterPCRequest,
    ResendPCEmailRequest,
    SendPCEmailRequest,
)
from src.entities.email_protocol import EmailID

app = FastAPI()


async def validate_registered_pc_id(pc_id: PCId) -> PCId:
    pc = simulation.get_pcs()[pc_id - 1]
    if pc.email_address is None:
        raise HTTPException(status_code=409, detail="PC not registered")
    return pc_id


registered_pcs_router = APIRouter(
    prefix="/pcs/{pc_id}",
    dependencies=[Depends(validate_registered_pc_id)],
)


@app.get("/pcs", response_model=GetPCsResponse, tags=["PCs"])
def get_pcs():
    pcs = simulation.get_pcs()
    return {"pcs": {pc.address: pc.email_address for pc in pcs}}


@app.put("/pcs/{pc_id}/register", tags=["PCs"])
async def register_pc(pc_id: PCId, req: RegisterPCRequest):
    pcs = simulation.get_pcs()
    pc = pcs[pc_id - 1]

    if pc.email_address is not None:
        raise HTTPException(status_code=409, detail="PC already registered")
    if req.address in [pc.email_address for pc in pcs]:
        raise HTTPException(status_code=409, detail="Address already registered")

    await pc.email_connect(req.address)


@registered_pcs_router.put("/unregister", tags=["PCs"])
async def unregister_pc(pc_id: PCId):
    pc = simulation.get_pcs()[pc_id - 1]
    await pc.email_disconnect()


@registered_pcs_router.get(
    "/emails", response_model=GetPCEmailsResponse, tags=["Emails"]
)
def get_pc_emails(pc_id: PCId):
    pc = simulation.get_pcs()[pc_id - 1]
    sent = [Email.from_dataclass(e) for e in pc.sent_emails]
    received = [Email.from_dataclass(e) for e in pc.received_emails]
    return {"sent": sent, "received": received}


@registered_pcs_router.post("/emails", tags=["Emails"])
async def send_pc_email(pc_id: PCId, req: SendPCEmailRequest):
    pc = simulation.get_pcs()[pc_id - 1]
    try:
        await pc.send_email(req.to, req.subject, req.body, req.in_reply_to)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@registered_pcs_router.post("/emails/{email_id}", tags=["Emails"])
async def resend_pc_email(pc_id: PCId, email_id: EmailID, req: ResendPCEmailRequest):
    pc = simulation.get_pcs()[pc_id - 1]
    try:
        await pc.resend_email(email_id, req.to)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


app.include_router(registered_pcs_router)

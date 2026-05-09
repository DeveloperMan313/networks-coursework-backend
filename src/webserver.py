from fastapi import APIRouter, Depends, FastAPI, HTTPException

from src import simulation
from src.entities.api import GetPCsResponse, PCId, RegisterPCRequest

app = FastAPI()


async def validate_registered_pc_id(pc_id: PCId) -> PCId:
    pc = simulation.get_pcs()[pc_id - 1]
    if pc.email_address is None:
        raise HTTPException(status_code=409, detail="PC not registered")
    return pc_id


registered_pcs_router = APIRouter(
    prefix="/pcs/{pc_id}",
    tags=["PCs"],
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


@registered_pcs_router.put("/unregister")
async def unregister_pc(pc_id: PCId):
    pc = simulation.get_pcs()[pc_id - 1]
    await pc.email_disconnect()


app.include_router(registered_pcs_router)

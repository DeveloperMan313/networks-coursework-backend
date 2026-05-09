from typing import Annotated, Dict

from pydantic import AfterValidator, BaseModel

from src.entities.email_protocol import EmailAddress
from src.physical import PCAddress
from src.simulation import get_pcs

# entities


def validate_pc_id(value: int) -> int:
    pcs_len = len(get_pcs())
    if not (1 <= value <= pcs_len):
        raise ValueError(f"must be 1–{pcs_len}")
    return value


PCId = Annotated[int, AfterValidator(validate_pc_id)]


# requests and responses


class GetPCsResponse(BaseModel):
    pcs: Dict[PCAddress, EmailAddress | None]


class RegisterPCRequest(BaseModel):
    address: EmailAddress

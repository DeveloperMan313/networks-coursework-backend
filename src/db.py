import json
import os
from typing import Dict, List

from src.entities.api import Email, EmailAddress
from src.physical import PCAddress

DB_FNAME = "db.json"

_db: Dict[PCAddress, Dict[EmailAddress, List[Email]]] = {}

_db_active: bool = False


def db_init():
    global _db, _db_active
    if os.path.exists(DB_FNAME) and os.path.isfile(DB_FNAME):
        with open(DB_FNAME, "r") as f:
            data: Dict[PCAddress, Dict[EmailAddress, List[str]]] = json.load(f)
            _db = {
                pc_addr: {
                    email_addr: [Email.model_validate_json(e) for e in email_jsons]
                    for email_addr, email_jsons in pc_emails.items()
                }
                for pc_addr, pc_emails in data.items()
            }
    _db_active = True


def db_get_pc_emails(address: PCAddress, email_address: EmailAddress) -> List[Email]:
    address_s = str(address)
    if not _db_active or address_s not in _db or email_address not in _db[address_s]:
        return []
    return _db[address_s][email_address]


def db_save_pc_email(address: PCAddress, email_address: EmailAddress, email: Email):
    if not _db_active:
        return
    if address not in _db:
        _db[address] = {}
    if email_address not in _db[address]:
        _db[address][email_address] = []
    _db[address][email_address] = [
        e for e in _db[address][email_address] if e.id != email.id
    ]
    _db[address][email_address].append(email)
    data: Dict[PCAddress, Dict[EmailAddress, List[str]]] = {
        pc_addr: {
            email_addr: [e.model_dump_json() for e in emails]
            for email_addr, emails in pc_emails.items()
        }
        for pc_addr, pc_emails in _db.items()
    }
    with open(DB_FNAME, "w") as f:
        json.dump(data, f)

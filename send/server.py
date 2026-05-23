import os
import secrets
import base64
import time
from typing import Annotated

from fastapi import FastAPI, Query, Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

import sendMessageToPowerstream_pb2 as pb

app = FastAPI(
    title="Powerstream API",
    version="1.0.0",
)
security = HTTPBearer()
API_TOKEN = os.getenv("POWERSTREAM_API_TOKEN")
DEVICE_SN = os.getenv("POWERSTREAM_DEVICE_SN")

if not API_TOKEN:
    raise RuntimeError("POWERSTREAM_API_TOKEN muss gesetzt sein")
if not DEVICE_SN:
    raise RuntimeError("POWERSTREAM_DEVICE_SN muss gesetzt sein")

def require_auth(credentials: Annotated[HTTPAuthorizationCredentials, Security(security)]):
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Ungültiges Auth-Schema")
    if not secrets.compare_digest(credentials.credentials, API_TOKEN):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Ungültiger API-Token")

def build_powerstream_message(value: int) -> bytes:
    if not (0 <= value <= 8000):
        raise ValueError("Protobuf-Wert außerhalb des erlaubten Bereichs")

    msg = pb.setMessage()
    msg.header.pdata.value = value
    msg.header.src = 32
    msg.header.dest = 53
    msg.header.d_src = 1
    msg.header.check_type = 3
    msg.header.cmd_func = 20
    msg.header.cmd_id = 129
    msg.header.need_ack = 1
    msg.header.seq = 1714141234 #int(time.time())    It would probably be good to use the current time instead, but I used this one in my testing for so long, that I just left it, because "never change a running system"
    msg.header.version = 19
    msg.header.payload_ver = 1
    msg.header.device_sn = DEVICE_SN

    setattr(msg.header, "from", "ios")
    msg.header.data_len = msg.header.pdata.ByteSize()
    return msg.SerializeToString()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/encodePermanentWatts")
def encode_powerstream(
    _: Annotated[None, Security(require_auth)],
    value: Annotated[int, Query(ge=0, le=800)]
):
    payload = build_powerstream_message(value * 10) # Mit 10 multiplizieren, da im Protobuf 8000 für 800 Watt stehen
    return {
        "value": value,
        "base64": base64.b64encode(payload).decode("ascii"),
    }

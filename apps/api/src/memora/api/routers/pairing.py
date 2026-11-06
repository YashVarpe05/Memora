"""Pairing endpoints, and the check that makes the token mean something.

The QR flow:

    laptop:  POST /pair/start   -> {code, url, expires_at}   rendered as a QR
    phone:   POST /pair/claim   -> {device_token}            stored in SecureStorage
    phone:   every request      -> Authorization: Bearer <device_token>

`require_paired_device` is the half that matters. A token nobody checks is decoration.
"""

from __future__ import annotations

import secrets
import socket
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from memora.api.deps import SettingsDep, current_user_id
from memora.services.pairing import PairingStore, store

router = APIRouter(tags=["pairing"])


class PairingStart(BaseModel):
    code: str
    # What the phone should call. Discovered rather than configured, so the QR works on
    # whatever address the hotspot handed out.
    url: str
    expires_at: str


class PairingClaim(BaseModel):
    code: str = Field(min_length=1, max_length=128)


class DeviceToken(BaseModel):
    device_token: str


class PairingStatus(BaseModel):
    devices_paired: int
    pairing_required: bool


def lan_address(port: int) -> str:
    """This machine's address on the network the phone is on.

    Uses a UDP socket to a routable address to learn which interface would be used. No
    packet is sent; it is the routing table being asked, not the internet - which matters
    because the demo network is a phone hotspot with no upstream connectivity.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))
        host = probe.getsockname()[0]
    except OSError:
        host = "127.0.0.1"
    finally:
        probe.close()
    return f"http://{host}:{port}"


def get_store() -> PairingStore:
    return store()


StoreDep = Annotated[PairingStore, Depends(get_store)]


async def require_paired_device(
    request: Request, settings: SettingsDep, pairings: StoreDep
) -> None:
    """Reject anything from an unpaired device.

    Loopback is exempt: the laptop's own browser is the owner sitting at the machine, and
    requiring it to pair with itself would mean showing a QR to scan with the screen the
    QR is on.

    Everything else needs the token. On a phone hotspot the API is reachable by anyone
    who joined, and it serves the owner's identity documents.
    """
    if not settings.require_pairing and not settings.is_production:
        return

    client = request.client.host if request.client else ""
    if not settings.is_production and client in ("127.0.0.1", "::1", "localhost"):
        return

    header = request.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else None
    if not pairings.is_paired(token):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "This device is not paired. Scan the QR code on the Memora window.",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_local_operator(request: Request, settings: SettingsDep) -> None:
    """The owner at the keyboard, not a device on the network.

    Minting and revoking pairings is not a paired-device power, it is an operator power,
    so it is gated on loopback rather than on a token. Without this, pairing enforces
    nothing at all: any phone on the hotspot could POST /pair/start, POST /pair/claim the
    code it just minted, and hold a valid device token two unauthenticated requests after
    joining the network. `require_paired_device` would then wave it through, because the
    token is genuine - it was issued to an attacker by design.

    `/pair/claim` is deliberately NOT behind this. The phone has no token when it claims;
    that request is the bootstrap. It is safe open because the code is 48 bits, single-use
    and expires in five minutes, and with `/pair/start` closed an attacker cannot mint one
    to claim - only guess.
    """
    if not settings.require_pairing and not settings.is_production:
        return

    if settings.operator_secret and secrets.compare_digest(
        request.headers.get("x-memora-operator", ""), settings.operator_secret
    ):
        return
    if settings.is_production:
        raise HTTPException(403, "An operator credential is required.")
    client = request.client.host if request.client else ""
    if client not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Pairing is started from the computer running Memora.",
        )


LocalOnly = [Depends(require_local_operator)]


@router.post("/pair/start", response_model=PairingStart, dependencies=LocalOnly)
async def start_pairing(settings: SettingsDep, pairings: StoreDep) -> PairingStart:
    """Called by the laptop to produce a QR. Loopback only - pairing is started by
    whoever is sitting at the machine, which is the whole point."""
    pairing = pairings.start()
    return PairingStart(
        code=pairing.code,
        url=settings.public_api_url or lan_address(settings.api_port),
        expires_at=pairing.expires_at.isoformat(timespec="seconds"),
    )


@router.post("/pair/claim", response_model=DeviceToken)
async def claim_pairing(payload: PairingClaim, pairings: StoreDep) -> DeviceToken:
    token = pairings.claim(payload.code)
    if token is None:
        # One message for unknown, expired and already-claimed. Distinguishing them
        # would tell a guesser which half of the guess was right.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "That pairing code is not valid. Show a new one."
        )
    return DeviceToken(device_token=token)


@router.get("/pair/status", response_model=PairingStatus, dependencies=LocalOnly)
async def pairing_status(settings: SettingsDep, pairings: StoreDep) -> PairingStatus:
    return PairingStatus(
        devices_paired=pairings.device_count,
        pairing_required=settings.require_pairing,
    )


@router.post("/pair/revoke", response_model=PairingStatus, dependencies=LocalOnly)
async def revoke_pairings(settings: SettingsDep, pairings: StoreDep) -> PairingStatus:
    """Unpair every device. Loopback only, so a phone on the hotspot cannot unpair the
    owner's devices - which would be a denial of service against the demo."""
    pairings.revoke_all()
    return PairingStatus(devices_paired=0, pairing_required=settings.require_pairing)


@router.get("/device/identity", dependencies=[Depends(require_paired_device)])
async def device_identity(user_id: Annotated[UUID, Depends(current_user_id)]) -> dict[str, str]:
    return {"device_id": str(user_id)}

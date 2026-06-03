"""Auth routes — service token infrastructure removed (plaintext export ban).

All service-to-service auth now goes through the proxy/sign/d-class interfaces,
which never expose plaintext secrets to the caller.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])

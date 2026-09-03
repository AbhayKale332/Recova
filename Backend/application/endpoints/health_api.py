"""Health endpoint used to confirm that the recovery API is available."""

from fastapi import APIRouter

router =APIRouter (tags =["Health"])

@router .get ("/health")
def health_check ():
    return {"status":"ok","service":"revenue-recovery-engine-api"}

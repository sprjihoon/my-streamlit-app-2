"""Inbound APIRouter. Prefix and tags match the former inbound module."""
from fastapi import APIRouter

router = APIRouter(prefix="/inbound", tags=["inbound"])

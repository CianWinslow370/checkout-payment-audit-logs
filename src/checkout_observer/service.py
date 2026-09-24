"""HTTP entry point for checkout payment logging and search."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from .checkout_audit import InfraiError, InfraiLogs, PaymentEvent, process_payment

app = FastAPI(title="Checkout payment audit")


class PaymentRequest(BaseModel):
    event_id: str = Field(min_length=1)
    order_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    payment_status: Literal["captured", "declined", "refunded"]
    risk_score: int = Field(ge=0, le=100)


class PaymentResponse(BaseModel):
    order_id: str
    action: Literal["send_receipt", "manual_review", "record_only"]
    notify_customer: bool


def get_logs() -> InfraiLogs:
    return InfraiLogs()


def client_error(error: InfraiError) -> HTTPException:
    status = error.status_code if 400 <= error.status_code < 500 else 502
    return HTTPException(status_code=status, detail={"code": error.code, "message": str(error)})


@app.post("/payments", response_model=PaymentResponse)
def accept_payment(payload: PaymentRequest, logs: InfraiLogs = Depends(get_logs)) -> PaymentResponse:
    event = PaymentEvent(**payload.model_dump())
    try:
        decision = process_payment(event, logs)
    except InfraiError as error:
        raise client_error(error) from error
    return PaymentResponse(order_id=event.order_id, **decision.__dict__)


@app.get("/orders/{order_id}/logs")
def search_payment_logs(
    order_id: str,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    logs: InfraiLogs = Depends(get_logs),
) -> dict:
    try:
        return logs.search_order(order_id, limit)
    except InfraiError as error:
        raise client_error(error) from error


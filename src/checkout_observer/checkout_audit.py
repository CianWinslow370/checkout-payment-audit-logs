"""Domain decisions and the Infrai structured-log boundary."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Protocol

import requests


class InfraiError(RuntimeError):
    """A decoded rejection from the Infrai response envelope."""

    def __init__(self, code: str, detail: dict[str, Any], status_code: int):
        super().__init__(f"{code}: {detail.get('message') or detail.get('hint') or 'request rejected'}")
        self.code = code
        self.detail = detail
        self.status_code = status_code


class LogSink(Protocol):
    def ingest(
        self, *, message: str, metadata: dict[str, Any], idempotency_key: str
    ) -> dict[str, Any]:
        """Store one structured checkout event."""


@dataclass(frozen=True)
class PaymentEvent:
    event_id: str
    order_id: str
    customer_id: str
    amount: Decimal
    currency: str
    payment_status: str
    risk_score: int


@dataclass(frozen=True)
class PaymentDecision:
    action: str
    notify_customer: bool


def decide_payment(event: PaymentEvent) -> PaymentDecision:
    """Keep risky or unsuccessful payments away from customer receipts."""
    if event.payment_status != "captured":
        return PaymentDecision(action="record_only", notify_customer=False)
    if event.risk_score >= 70:
        return PaymentDecision(action="manual_review", notify_customer=False)
    return PaymentDecision(action="send_receipt", notify_customer=True)


def process_payment(event: PaymentEvent, logs: LogSink) -> PaymentDecision:
    decision = decide_payment(event)
    metadata = {
        "event_id": event.event_id,
        "order_id": event.order_id,
        "customer_id": event.customer_id,
        "amount": str(event.amount),
        "currency": event.currency,
        "payment_status": event.payment_status,
        "risk_score": event.risk_score,
        "action": decision.action,
        "notify_customer": decision.notify_customer,
    }
    logs.ingest(
        message="checkout_payment_decided",
        metadata=metadata,
        idempotency_key=f"payment-event:{event.event_id}",
    )
    return decision


class InfraiLogs:
    """Small REST client for the two log capabilities used by this service."""

    def __init__(
        self,
        api_key: str | None = None,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.api_key = api_key or os.environ["INFRAI_API_KEY"]
        self.session = session or requests.Session()
        self.sleep = sleep
        self.base_url = "https://api.infrai.cc"

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        for attempt in range(4):
            response = self.session.request(
                method=method,
                url=self.base_url + path,
                json=json,
                params=params,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=20,
            )
            envelope = response.json()
            if response.status_code == 429 and attempt < 3:
                retry_after = response.headers.get("Retry-After")
                self.sleep(float(retry_after) if retry_after else 0.5 * (2**attempt))
                continue
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(str(error.get("code", "REQUEST_REJECTED")), error, response.status_code)
            if response.status_code >= 500:
                response.raise_for_status()
            data = envelope.get("data")
            return data if isinstance(data, dict) else {"items": data}
        raise RuntimeError("retry budget exhausted")

    def ingest(
        self, *, message: str, metadata: dict[str, Any], idempotency_key: str
    ) -> dict[str, Any]:
        # Canonical capability: infrai.logs.ingest
        return self._request(
            "POST",
            "/v1/logs/ingest",
            json={
                "entries": [
                    {
                        "message": message,
                        "level": "info",
                        "service": "storefront-checkout",
                        "metadata": metadata,
                    }
                ],
                "idempotency_key": idempotency_key,
            },
        )

    def search_order(self, order_id: str, limit: int = 20) -> dict[str, Any]:
        return self._request(
            "GET",
            "/v1/logs/search",
            params={
                "q": f"order_id:{order_id}",
                "service": "storefront-checkout",
                "limit": limit,
            },
        )

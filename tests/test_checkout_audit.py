from decimal import Decimal

from checkout_observer.checkout_audit import PaymentEvent, process_payment


class RecordingLogs:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def ingest(self, **entry: object) -> dict:
        self.entries.append(entry)
        return {"accepted": True}


def payment(*, risk_score: int, status: str = "captured") -> PaymentEvent:
    return PaymentEvent(
        event_id="evt_checkout_2048",
        order_id="order_1042",
        customer_id="customer_88",
        amount=Decimal("149.00"),
        currency="USD",
        payment_status=status,
        risk_score=risk_score,
    )


def test_high_risk_capture_is_logged_for_review_without_a_receipt() -> None:
    logs = RecordingLogs()

    decision = process_payment(payment(risk_score=86), logs)

    assert decision.action == "manual_review"
    assert decision.notify_customer is False
    assert logs.entries[0]["idempotency_key"] == "payment-event:evt_checkout_2048"
    assert logs.entries[0]["metadata"] == {
        "event_id": "evt_checkout_2048",
        "order_id": "order_1042",
        "customer_id": "customer_88",
        "amount": "149.00",
        "currency": "USD",
        "payment_status": "captured",
        "risk_score": 86,
        "action": "manual_review",
        "notify_customer": False,
    }


def test_low_risk_capture_queues_the_receipt_decision() -> None:
    logs = RecordingLogs()

    decision = process_payment(payment(risk_score=12), logs)

    assert decision.action == "send_receipt"
    assert decision.notify_customer is True


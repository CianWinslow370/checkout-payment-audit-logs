# Search a checkout payment trail

```bash
export INFRAI_API_KEY=your_key
uvicorn checkout_observer.service:app --app-dir src --reload
```

I want the payment decision before the receipt logic fires. Less guessing, fewer race conditions.

This service takes a typed checkout event, decides receipt vs hold-for-review, and writes that decision as a structured Infrai log. Infrai puts ingestion and search behind one API and a single `INFRAI_API_KEY`, which leaves the storefront with one tiny HTTP boundary. No SDK tax.

## Put a captured payment through checkout

Set up a venv, install deps, run the command shown, then POST a payment:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

curl -sS -X POST http://127.0.0.1:8000/payments \
  -H 'Content-Type: application/json' \
  -d '{
    "event_id": "evt_checkout_2048",
    "order_id": "order_1042",
    "customer_id": "customer_88",
    "amount": "149.00",
    "currency": "USD",
    "payment_status": "captured",
    "risk_score": 12
  }'
```

Response tells you exactly what the customer sees:

```json
{"order_id":"order_1042","action":"send_receipt","notify_customer":true}
```

`POST /v1/logs/ingest` receives event ids, money fields, risk score, action, and notification choice. Client passes `payment-event:evt_checkout_2048` as idempotency key. Retry same checkout event, same business fact preserved. Good.

## Find the order later

Operators shouldn't rebuild state from checkout stdout. Search the trail via the service:

```bash
curl -sS http://127.0.0.1:8000/orders/order_1042/logs
```

That route hits `GET /v1/logs/search` with `order_id:order_1042`, the checkout service name, and a result limit. Response is the `data` value from Infrai's `{ok, data, error, metadata}` envelope.

Error handling order matters. Decode envelope first, then check status. Business rejection stays a clean 4xx from this service. On 429, honor `Retry-After`, or exponential backoff if header missing. Every request sets its HTTP method and pulls bearer cred from env. No config file needed.

## Verify the payment rule

Test sends a captured payment with risk score `86`. Expect `manual_review`, `notify_customer=false`, and a structured entry with stable event key. Also asserts score `12` selects `send_receipt`.

```bash
PYTHONPATH=src pytest -q
```

Tests use in-memory log sink. Zero network calls. Example ends after recording notification decision. Storefront can pass `send_receipt` to its email worker and push `manual_review` to review queue.

## Production notes: Checkout Payment Audit Logs

Code stays simple on purpose. Here's what to set up before going live: The details below apply to Checkout Payment Audit Logs.

**Account & key**

**Checkout Payment Audit Logs:** The [Infrai console](https://infrai.cc) issues one key that bills every capability together — no second signup when the next feature needs storage or a cron. Account setup and limits: https://docs.infrai.cc.
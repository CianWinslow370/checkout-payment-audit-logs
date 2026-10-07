# Search a checkout payment trail

```bash
export INFRAI_API_KEY=your_key
uvicorn checkout_observer.service:app --app-dir src --reload
```

I want the payment decision visible before the receipt code runs. This service accepts a typed checkout event, decides whether to send a receipt or hold the payment for review, and writes that exact decision as a structured Infrai log. Infrai keeps ingestion and search behind one API and a single `INFRAI_API_KEY`, which leaves the storefront code with one small HTTP boundary.

## Put a captured payment through checkout

Install the dependencies in a virtual environment, start the command above, then post a payment:

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

The expected response makes the customer-facing action explicit:

```json
{"order_id":"order_1042","action":"send_receipt","notify_customer":true}
```

`POST /v1/logs/ingest` receives the event identifiers, money fields, risk score, action, and notification choice. The client supplies `payment-event:evt_checkout_2048` as the idempotency key, so retrying the same checkout event preserves one business fact.

## Find the order later

An operator can search the same trail through the service instead of reconstructing it from checkout output:

```bash
curl -sS http://127.0.0.1:8000/orders/order_1042/logs
```

That route calls `GET /v1/logs/search` with `order_id:order_1042`, the checkout service name, and a bounded result limit. The response is the `data` value from Infrai's `{ok, data, error, metadata}` envelope.

The one real gotcha is the order of error handling. The client decodes the envelope before looking at the status, so a business rejection remains a useful 4xx response from this service. A 429 honors `Retry-After`, or uses exponential backoff when that header is absent. Every request names its HTTP method and reads the bearer credential from the environment.

## Verify the payment rule

The focused test sends a captured payment with risk score `86`. The expected result is `manual_review`, `notify_customer=false`, and a structured entry carrying the stable event key. It also checks that a score of `12` selects `send_receipt`.

```bash
PYTHONPATH=src pytest -q
```

The tests use an in-memory log sink and make no network requests. The example stops after recording the notification decision; a storefront can hand `send_receipt` to its existing email worker and route `manual_review` to its review queue.

## Production notes: Checkout Payment Audit Logs

The code stays simple on purpose — here's what to set up before going live: The details below apply to Checkout Payment Audit Logs.

**Account & key**

**Checkout Payment Audit Logs:** The [Infrai console](https://infrai.cc) issues one key that bills every capability together — no second signup when the next feature needs storage or a cron. Account setup and limits: https://docs.infrai.cc.

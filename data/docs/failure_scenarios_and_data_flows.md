# Failure Scenarios and Data Flows

## Data flow: new subscription purchase
1. The browser sends a checkout request to the API Gateway, which validates the token with the Authentication Service.
2. The API Gateway routes the request to the Checkout Service, which creates an order in the Billing Database.
3. The Checkout Service calls the Payment Service, which charges the customer through PayFlow.
4. The Payment Service publishes payment.completed to the Event Queue.
5. The Billing Service consumes the event and creates the invoice and PDF. The Notification Service consumes the same event and emails a receipt through MailBridge.

## Data flow: new account sign-up
1. The browser sends a sign-up request to the API Gateway, which forwards it to the Authentication Service without token validation.
2. The Authentication Service creates the account in the User Database and stores the session in the Session Cache.
3. The Authentication Service publishes user.registered to the Event Queue.
4. The Notification Service consumes the event, looks up preferences from the User Service, and sends a welcome email through MailBridge.

## Scenario: Authentication Service outage
During an outage the gateway cannot validate tokens, so it returns HTTP 503 for protected routes. Sign-in and sign-up also fail. Public routes such as the Pricing Page keep working. Backend services keep running but receive no user traffic. Background work that does not depend on the Authentication Service, such as payment reconciliation and invoice rendering, continues.

## Scenario: Session Cache outage
The Authentication Service falls back to the User Database for revocation checks, and the gateway switches to in-memory rate limits. No feature becomes unavailable, but latency increases. If the outage is prolonged, the extra read load on the User Database is the main risk.

## Scenario: Payment Provider outage
Subscription Checkout shows "payment processing" and no invoices are created until payments are confirmed. Invoice Download for existing invoices and Usage Reports are unaffected.

## Scenario: Event Queue outage
Payments still succeed. Payment events wait in the outbox, so invoices and receipts are delayed rather than lost. Welcome emails for new sign-ups during the outage may be lost.
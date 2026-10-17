# API Gateway

## Responsibilities
The API Gateway is the single entry point for all client traffic. It terminates TLS, applies rate limits, routes requests to backend services, and enforces authentication on protected routes.

## Authentication enforcement
For every protected route, the API Gateway calls the Authentication Service to validate the bearer token before forwarding the request. Public routes, such as the Pricing Page, skip token validation. The sign-in and sign-up endpoints are forwarded to the Authentication Service directly, because callers do not have a token yet. If token validation cannot be completed, the API Gateway rejects the request with HTTP 503 instead of forwarding it unauthenticated.

## Routing
The API Gateway routes by path prefix. Requests under /auth go to the Authentication Service. Requests under /profile go to the User Service. Requests under /checkout go to the Checkout Service. Requests under /invoices go to the Billing Service. Requests under /reports go to the Reporting Service.

## Rate limiting
The API Gateway keeps rate-limit counters in the Session Cache. If the Session Cache is unreachable, the gateway falls back to a conservative in-memory limit per gateway instance and continues serving traffic.

## Timeouts and retries
The API Gateway uses a 2-second timeout when calling the Authentication Service and retries once. It does not cache token validation results, so every protected request triggers a fresh validation call.
# Lumio Platform Overview

Lumio is a fictional subscription-based project management SaaS. This document is the high-level map; each service is described in its own document.

## User-facing features
Lumio exposes seven user-facing features:
- Sign-in and Sign-up lets people create accounts and log in.
- Profile Settings lets users edit their name, email address, and notification preferences.
- Subscription Checkout lets a team buy or change a paid plan.
- Invoice Download lets customers download PDF invoices for past payments.
- Usage Reports lets administrators export monthly usage reports.
- Email Notifications sends welcome emails, payment receipts, and payment failure alerts.
- Pricing Page is a public page listing plans and prices. It requires no login.

## Request path
All browser and mobile traffic enters through the API Gateway. The API Gateway routes each request to a backend service. Backend services are not exposed to the internet directly. Protected routes require the API Gateway to validate the caller's token with the Authentication Service before routing.

## Feature to service mapping
Sign-in and Sign-up is served by the Authentication Service. Profile Settings is served by the User Service. Subscription Checkout is served by the Checkout Service. Invoice Download is served by the Billing Service. Usage Reports is served by the Reporting Service. Email Notifications is delivered by the Notification Service. The Pricing Page is served directly by the API Gateway from static content.

## Shared infrastructure
Lumio uses four data stores and one message broker: the User Database (PostgreSQL), the Billing Database (PostgreSQL), the Session Cache (Redis), Invoice Storage (an object store), and the Event Queue (RabbitMQ). Two external providers are used: the Payment Provider PayFlow, which processes card payments, and the Email Provider MailBridge, which delivers email.
# Event Queue and Notification Service

## Event Queue
The Event Queue is a RabbitMQ cluster with three nodes. It carries three event types: user.registered, payment.completed, and payment.failed. Messages are persisted to disk and acknowledged only after a consumer finishes processing.

## Publishers and consumers
The Authentication Service publishes user.registered. The Payment Service publishes payment.completed and payment.failed. The Billing Service consumes payment.completed. The Notification Service consumes all three event types.

## Notification Service
The Notification Service sends email through the external Email Provider, MailBridge. For each event it asks the User Service for the recipient's address and preferences, renders a template, and calls MailBridge. It powers the Email Notifications feature.

## Delivery guarantees
Delivery is at-least-once, so consumers must tolerate duplicate messages. A message that fails processing is retried five times with exponential backoff and then moved to a dead-letter queue.

## Queue outage behavior
If the Event Queue is unavailable, the Payment Service writes events to an outbox table in the Billing Database, and a relay publishes them when the queue returns. The Authentication Service has no outbox, so user.registered events published during an outage are lost and welcome emails may not be sent.
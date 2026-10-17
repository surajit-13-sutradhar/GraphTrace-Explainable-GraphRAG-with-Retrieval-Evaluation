# Billing Service and Reporting Service

## Billing Service
The Billing Service creates invoices. It consumes payment.completed events from the Event Queue, writes an invoice record to the Billing Database, and renders a PDF that is stored in Invoice Storage.

## Invoice Download
The Invoice Download feature is served by the Billing Service. When a customer requests an invoice, the Billing Service reads the invoice record from the Billing Database and fetches the PDF from Invoice Storage. If Invoice Storage is unavailable, the invoice list still loads but downloads fail.

## Billing Database
The Billing Database is a PostgreSQL 15 cluster that stores orders, payment attempts, and invoices. It is written to by the Checkout Service, the Payment Service, and the Billing Service.

## Reporting Service
The Reporting Service powers Usage Reports. It reads from the Reporting Replica, a read-only replica of the Billing Database, so heavy report queries do not slow down checkout. The Reporting Service never writes to the Billing Database.

## Replication lag
The Reporting Replica typically lags the Billing Database by under 30 seconds, so Usage Reports may omit very recent payments. If the Billing Database primary is down, Usage Reports continue to work from the replica, with stale data.
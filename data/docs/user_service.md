# User Service and User Database

## User Service responsibilities
The User Service manages profile data: display name, email address, time zone, and notification preferences. It powers the Profile Settings feature.

## Data access
The User Service reads from and writes to the User Database. It does not use the Session Cache. Its only callers are the API Gateway and the Notification Service. The User Service itself calls no other service.

## User Database
The User Database is a PostgreSQL 15 cluster with one primary and two replicas. It stores accounts, password hashes, profile data, and token revocation records. The Authentication Service writes accounts, password hashes, and revocation records. The User Service writes profile data.

## Failover
If the User Database primary fails, automatic failover promotes a replica within about 60 seconds. During failover, writes fail, so profile updates and sign-ups fail, while reads from replicas continue.

## Notification preferences
The Notification Service calls the User Service to look up a user's email address and notification preferences before sending any email. If the User Service is unavailable, the Notification Service retries the message later and does not drop it.
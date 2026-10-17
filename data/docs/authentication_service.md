# Authentication Service

## Responsibilities
The Authentication Service handles sign-up, sign-in, and token validation. It issues signed JSON Web Tokens (JWTs) that are valid for 15 minutes, together with refresh tokens that are valid for 30 days.

## Data dependencies
The Authentication Service reads and writes account records and token revocation records in the User Database. It stores active sessions and refresh-token records in the Session Cache. The Authentication Service does not call the User Service.

## Token validation
Token validation first checks the JWT signature locally. It then checks the Session Cache to confirm that the session has not been revoked.

## Session Cache fallback
If the Session Cache is unavailable, the Authentication Service falls back to checking revocation records in the User Database. Validation keeps working, but p95 latency rises from about 5 ms to about 40 ms, and the User Database receives much more read traffic.

## Events
After a successful sign-up, the Authentication Service publishes a user.registered event to the Event Queue. The Notification Service consumes this event to send the welcome email.

## Availability
The Authentication Service runs as three stateless instances behind an internal load balancer. If the User Database is unavailable, sign-in and sign-up fail. Token validation for sessions already present in the Session Cache continues to succeed.
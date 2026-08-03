<!-- source: https://internal.example.com/runbooks/it/vpn-connect-hangs -->

# VPN client hangs on connecting

## Symptoms

- VPN client stays on "Connecting..." for 30+ seconds.
- Users report failures after certificate or client updates.

## Common causes

1. Stale client profile after gateway certificate rotation.
2. Local firewall blocking UDP 443.
3. Cached credentials from an expired session.

## Resolution steps

1. Ask the user to quit the VPN client completely and relaunch it.
2. Remove and re-import the latest VPN profile from the self-service portal.
3. Verify the system clock is correct; TLS handshake fails on large drift.
4. If errors mention `certificate_pin_mismatch`, push the refreshed gateway cert bundle.

## Escalation

Escalate to network on-call if more than 10 users report handshake failures within 15 minutes.

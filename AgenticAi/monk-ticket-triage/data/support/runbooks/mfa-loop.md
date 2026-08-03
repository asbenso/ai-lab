<!-- source: https://internal.example.com/runbooks/auth/mfa-loop -->

# MFA loop on login

## Symptoms

- User enters their MFA code from an authenticator app.
- After submitting, they are redirected back to the login page.
- Repeats indefinitely.

## Common causes

1. Device clock drift. The authenticator app on the user's phone is more than 30 seconds out of sync with our servers.
2. Replay attack protection misfired when the user double-clicks Submit.
3. Cached session token from a prior failed attempt is still in the user's browser.

## Resolution steps

1. Ask the user to fully close the authenticator app and reopen it.
2. Ask the user to clear cookies for our domain and try again from a fresh browser tab.
3. If still failing, manually reset the user's MFA device from the admin panel.

## Escalation

Escalate to the auth-platform on-call if the user reports multiple MFA loops across multiple sessions in the same day.

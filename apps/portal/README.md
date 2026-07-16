# Public SaaS portal

This dependency-free static application is the public and tenant-account surface for
the working modular-monolith slice. It reads the public, versioned plan catalog without
authentication and can read subscription/entitlement state with a scoped tenant token.

The portal deliberately renders `price_not_configured` and `contact_sales` states
instead of inventing prices. Checkout and account-management buttons only redirect to a
URL returned by the API; provider secrets never enter the browser. The current token
field is a local POC boundary. Hosted operation requires OIDC authorization-code flow
with PKCE and secure server-side/provider sessions.

Run with the full stack:

```console
docker compose up --build
```

Then open `http://localhost:8081`. The API must allow that exact origin.

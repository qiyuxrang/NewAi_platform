# Dedicated Bridge authentication

Bridge HTTP requests and both WebSocket upgrade paths (`/ws` and `/api/terminal/ws`)
require `Authorization: Bearer <NANOBOT_PROXY__TOKEN>`. The token is the existing
dedicated container token. Missing, wrong, other-container and default `dev-token`
credentials are rejected before JSON parsing or WebSocket upgrade. Query tokens
do not authenticate to Bridge.

The platform validates browser JWTs, resolves the current user's container, and
sends its own server-side container token to Bridge. Browser JWT query values are
removed from forwarded file and HTTP requests. Direct container HTTP requests do
not use environment HTTP proxies. WebSocket relays use the existing dependency's
legacy client interface so the declared `websockets>=12` range remains supported.

For the existing local development URL overrides only, set
`PLATFORM_DEV_BRIDGE_TOKEN` to the same explicit token as the local Bridge's
`NANOBOT_PROXY__TOKEN`; empty or `dev-token` configuration fails closed. These
overrides use one development runtime and are unsuitable for independent employee
runtimes; production uses dedicated containers and their database tokens.

Isolated checks: `node scripts/check-bridge-auth.mjs` (after the existing private
Bridge checker dependencies are prepared) and `python -m unittest discover -s
platform/tests -p test_runtime_proxy_auth.py`. The first compiles only the auth
helper and tests ephemeral HTTP/WS gates. It does not compile the full runtime.

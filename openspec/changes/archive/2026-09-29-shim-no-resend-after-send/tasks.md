No `design.md`: the change narrows one retry condition and names the transport errors it trusts.

## 1. Shim

- [x] 1.1 In `_Bridge._handle_envelope`, resend after a transport failure only for `ConnectError` / `ConnectTimeout` or a method other than `tools/call`; otherwise rebind and emit a JSON-RPC error for the request id
- [x] 1.2 Keep the 401 path (rotated token) resending as before

## 2. Tests

- [x] 2.1 `test_shim_resend.py`: connect error resends a `tools/call`; read error after send does not resend a `tools/call` and emits an error; read error on `tools/list` resends; 401 resends

## 3. Docs

- [x] 3.1 `docs-site/architecture/mcp-gateway.md`: the shim's restart-recovery step states the resend rule

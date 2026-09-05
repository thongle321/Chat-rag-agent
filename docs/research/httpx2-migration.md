# httpx → httpx2 migration note

> Web sources not fetched (no network tool in this env). All claims below are
> grounded in the installed packages: `httpx2 2.12.0`, `httpx 0.28.1`,
> `logfire 4.41.0`, `opentelemetry-instrumentation-httpx 0.65b0`
> (versions per `backend/uv.lock`). Spot-check against
> https://pydantic.dev/docs/httpx2/get-started/ before executing.

## Install / package / import

- PyPI package is **`httpx2`** (coexists with `httpx`; separate `httpcore2` transport
  dep). Source: `backend/.venv/Lib/site-packages/httpx2-2.12.0.dist-info/`,
  `backend/uv.lock:1784` (`httpx2-2.12.0`).
- Import path: **`import httpx2`** / `from httpx2 import AsyncClient`.
  Source: `httpx2/__init__.py` exports `AsyncClient`, `Timeout`, `Response`, …
- `pyproject.toml`: **keep** `httpx>=0.28.0` (the `python-zalo-bot` SDK imports
  classic `httpx` internally — `zalo_bot/request/_httpx_request.py:3` does
  `import httpx` and builds `httpx.Timeout`/`httpx.AsyncClient`) and **add**
  `httpx2>=2.12`. The two clients coexist; nothing forces a flag-day.

## AsyncClient + timeout + POST/GET parity (all 1:1)

- `httpx2.AsyncClient(timeout=30)` / `timeout=10` / `timeout=<float>` — identical
  signature (`timeout: TimeoutTypes = DEFAULT_TIMEOUT_CONFIG`).
  Source: `httpx2/_client.py:1456` (`AsyncClient.__init__`).
- Default timeout is `Timeout(5.0)` — same 5 s default as classic httpx.
  Source: `httpx2/_config.py` (`DEFAULT_TIMEOUT_CONFIG`).
- `Timeout(connect, read, write, pool)` config object identical; `verify=<str>`
  and `cert=` are now **deprecated** (emit `DeprecationWarning`) — we use
  neither. Source: `httpx2/_config.py` (`create_ssl_context`, `Timeout`).
- `.post(url, json=…, headers=…, params=…)` / `.get(…)` / `.request(…)` kwargs
  identical. Source: `httpx2/_client.py:2021` (`AsyncClient.post`), `:1940` (`get`).
- `is_closed` / `await client.aclose()` exist — the shared-client pattern in
  `facebook.py`/`zalo.py` ports unchanged. Source: `httpx2/_client.py:171,215,2198`.

## Exception mapping (old → new): names are identical

| `httpx` (0.28) | `httpx2` (2.12) | Note |
|---|---|---|
| `httpx.ConnectError` | `httpx2.ConnectError` | same hierarchy |
| `httpx.HTTPStatusError` (`.response.status_code`) | `httpx2.HTTPStatusError` | same; raised by `raise_for_status()` |
| `httpx.TimeoutException` (base; `ConnectTimeout`/`ReadTimeout`/…) | `httpx2.TimeoutException` | same subclasses |
| `except Exception` probes | unchanged | still fine |

Hierarchy is unchanged: `HTTPError → RequestError → TransportError →
{TimeoutException, NetworkError(→ConnectError), …}`, plus `HTTPStatusError`.
Source: `httpx2/_exceptions.py` (module docstring + classes).

## Response API parity

- `.status_code`, `.text`, `.content`, `.headers` — identical.
  Source: `httpx2/_models.py:541` (`status_code`), `:650` (`text`), `:477` (content).
- `.raise_for_status()` — identical semantics, raises `HTTPStatusError`.
  Source: `httpx2/_models.py:793`.
- `.json()` = `json.loads(self.content)` — raises `json.JSONDecodeError`, which
  **is a `ValueError`**, so `shopify_global._rpc`'s `except ValueError` still
  catches malformed bodies. Source: `httpx2/_models.py:829`.

## Logfire: no tracing loss — keep `logfire.instrument_httpx()` as-is

- `instrument_httpx(client=None)` instruments **all clients from both installed
  libraries** via `HTTPXClientInstrumentor` (httpx) **and**
  `HTTPX2ClientInstrumentor` (httpx2). Per-client instances of either library
  are also accepted. Source: `logfire/_internal/main.py:1599`
  ("Instrument the `httpx` and `httpx2` modules…"), `logfire/_internal/integrations/httpx.py`
  (`_instrumentors_for_installed_modules`, `_instrumentor_for_client`).
- httpx2 side requires `opentelemetry-instrumentation-httpx>=0.65b0`, else
  httpx2 is skipped with a warning (or `RuntimeError` if httpx is absent).
  We have exactly `0.65b0` (`uv.lock:2891`) via the existing
  `logfire[fastapi,httpx,sqlalchemy]` extra (`pyproject.toml:21`,
  `uv.lock:2117`) — **no dependency change needed**.
- `main.py:36` (`logfire.instrument_httpx()`) needs **zero changes**.
- OTel reference (from Logfire docstring):
  https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/httpx/httpx.html

## Breaking gotchas

1. **Do NOT use `httpx2.alias_httpx()` here.** It must run before *anything*
   imports `httpx`/`httpcore` (else `RuntimeError: …already imported`) and is
   process-wide, hijacking third-party libs ("Libraries should never call
   this"). Our `lifespan` runs long after module imports (`facebook.py`,
   `zalo.py`, `zalo_bot`), so it would crash. Direct import swap only.
   Source: `httpx2/_alias.py` (`alias_httpx` docstring + `_alias` guard).
2. **Leave `python-zalo-bot` on classic httpx.** It constructs
   `httpx.Timeout`/`httpx.AsyncClient`/`httpx.AsyncHTTPTransport` internally and
   catches `httpx.TimeoutException`/`httpx.HTTPError`/`httpx.PoolTimeout`.
   Source: `zalo_bot/request/_httpx_request.py`. Only our own `_get_client` /
   `_zalo_set_webhook` in `app/api/zalo.py` migrate.
3. **Actual scope is 7 sites, not 6** (task missed the FB/Zalo shared clients):
   `shopify_global._rpc` ×1, `settings.py` ×4, `facebook.py` `_get_client` ×1,
   `zalo.py` `_get_client` (+ `_zalo_set_webhook` via the same client) ×1.
4. `verify=<str>` / `cert=` deprecation — not used by us; no action.
5. `Response.json()` failure mode stays `ValueError` — no `except` changes needed.

## Recommended minimal diff

One line per file — alias the import, since every used name is 1:1:

```diff
# backend/app/services/shopify_global.py, backend/app/api/settings.py
-import httpx
+import httpx2 as httpx
# backend/app/api/facebook.py, backend/app/api/zalo.py
-from httpx import AsyncClient
+from httpx2 import AsyncClient
# backend/pyproject.toml dependencies: add "httpx2>=2.12", keep "httpx>=0.28.0"
```

- Zero changes to `except` clauses, `raise_for_status`/`json()`/`status_code`
  usage, timeout values, `main.py` Logfire setup, or the FB/Zalo
  `_get_client`/`close_client` lifecycle.
- Then `uv sync`, `ruff check`, and re-run the admin probes
  (`/settings/test`, `/settings/models`, `/settings/shopify-catalog/test`).
- Optional (not minimal): rename usages to `httpx2.X` explicitly for clarity.

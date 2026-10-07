# Aditya Prints — factory order desk

Next.js App Router frontend and self-hosted FastAPI/MongoDB backend. Existing orders, parcels, bulk entry, requirements, challans, catalogues, parties, stock, production and team-access pages are preserved. Bills & Cash adds owner-private bill accounting and an administrator-wide ledger.

## Local factory installation (Linux)

Requirements: Node.js 20.12+ or supported newer LTS, Yarn, Python 3.11+, MongoDB 5+ (standalone supported). No hosted third-party API or cloud credentials are required. The browser interface works on desktop computers; this is not a native desktop installer.

1. Keep `.env` private and outside source control. Required values: `MONGO_URL`, `DB_NAME`, `NEXT_PUBLIC_BASE_URL` (the exact browser origin), `CORS_ORIGINS` (explicit trusted origins, no wildcard), `JWT_SECRET` (at least 64 random characters), `ADMIN_EMAIL`, `ADMIN_PASSWORD`, and `BACKEND_SOCKET` (an absolute private Unix-socket path writable by the service user). `PORT` chooses the Next.js listener. `PYTHON_EXECUTABLE` can point to your virtual environment. Never expose the socket to other users.
2. `python3 -m venv .venv` then `.venv/bin/pip install -r backend/requirements.txt`.
3. `yarn install --frozen-lockfile` then `yarn build`.
4. Run `PYTHON_EXECUTABLE=.venv/bin/python yarn start` as a dedicated unprivileged service user, managed by systemd or supervisor. The start script starts Next.js and the private backend and stops both together. Alternatively supervise the two processes separately using `yarn start:web` and `.venv/bin/python backend/run.py`.
5. Put HTTPS in front of the single Next.js listener. Authentication deliberately uses Secure HttpOnly cookies and therefore requires HTTPS. Route all browser requests through Next.js; do not expose FastAPI directly.
6. Set `FRAME_ANCESTORS="'self'"` for standalone factory hosting. This is configurable to allow trusted iframe embedding during preview; production should explicitly restrict it. Set `NEXT_TELEMETRY_DISABLED=1` to disable framework telemetry if desired.

`deploy/factory-api.conf` is an example for the current managed development workspace, not a portable production path configuration. Adjust paths for your server; runtime socket files are recreated, while all records and images persist in MongoDB.

## Features and accounting

- All original pages are real Next.js routes with the original warm brown/ivory palette and locally bundled Playfair Display / Plus Jakarta Sans / DM Mono fonts.
- Select a party before bulk entry. Existing text supports 3+ catalogue/volume items joined by `+`, `&`, or `and`, for example `sujal17 + shrishti 2 and saya 3`. Numbers are volume names, not quantities. Commas and party names embedded in parcel text are not parser separators; the parser was retained at the user's request.
- Bills use integer paise. Net cash issued = issues minus returned excess. Positive bill-minus-net is payable; positive net-minus-bill is cash to take back. Multiple cash entries are preserved, not overwritten. Users need Bills page permission and can only access their own bills; administrators can access all.
- Bill and cash saves use UUID idempotency keys. Cash entries and bill balances update atomically in one document. Bill changes retain history. Ledger limits are explicit rather than silently truncating records.
- Stock additions/corrections are durable, replayable operations. Stock-account balances and receipts update atomically, then ledger records finalize. Version-fenced recovery prevents double deductions; dispatched parcels retain a recovery marker. Reads and application startup repair interrupted work. This is recoverable consistency, not a claim of multi-document ACID transactions.
- Production-stage state and history update atomically. Stock, production, urgent requests, masters, users and requirements use bounded pages and database-side summaries. Form dropdowns intentionally fetch compact master options in shared, invalidated pages to preserve complete native selectors.
- Photos upload as 128 KiB chunks (up to 5 MiB); the server validates actual image type/dimensions. Chunks and final images persist in MongoDB. Incomplete uploads expire after one day. Images are only available to authenticated production users.

## Before real production use

The user explicitly retained the original test login for this workspace. **Rotate every credential from the original public repository before real use**, including JWT secret and administrator password. Reusing test secrets is not production-safe. Do not copy the original repository's `.env`, logs or old credential documents into version control.

Take consistent MongoDB backups, test restoration, secure the host/network, restrict filesystem access, configure service restart/log rotation, and load-test with realistic factory data and concurrent staff. Back up `photos` along with business collections. No application audit can guarantee that every possible defect is eliminated.

Production history is bounded to 2,000 entries per batch; Bills allow 2,000 cash entries and 100 bill edits; catalogues allow 1,000 volumes. Create new records when limits are reached. Interrupted stock recovery fails closed with a retry message instead of returning a knowingly stale balance.

See `test_result.md` for actual verified test coverage and `memory/` for audit notes. Test files are development tools, not scripts loaded in the browser. There are no app-level builder badges, analytics widgets, tracking scripts or migration scripts.

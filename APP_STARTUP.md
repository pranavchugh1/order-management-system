# App Startup Guide

This project runs a Next.js web app with a FastAPI backend and MongoDB.

## Requirements

- Node.js 20.12 or newer
- Yarn 1.22.22
- Python 3.11 or newer
- MongoDB 5 or newer, running locally or on a reachable server

## Configure

1. Create a `.env` file in the project root. Set `MONGO_URL`, `DB_NAME`, `NEXT_PUBLIC_BASE_URL`, `CORS_ORIGINS`, `JWT_SECRET`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD`.
2. For local Windows development, use a reachable MongoDB URL such as `mongodb://127.0.0.1:27017`, set `NEXT_PUBLIC_BASE_URL=http://localhost:3000` and `CORS_ORIGINS=http://localhost:3000`.
3. Set `BACKEND_SOCKET` to a private socket path supported by the runtime environment. The deployment example in `FACTORY_SETUP.md` uses a Unix socket; on Windows local development, check `scripts/start.mjs` for the supported backend connection configuration.

Keep the JWT secret and administrator password private. Do not commit `.env` to a public repository.

## Install dependencies

From the project root in PowerShell:

```powershell
yarn install --frozen-lockfile
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

## Start for development

Start the backend in one PowerShell window:

```powershell
.\.venv\Scripts\python.exe backend\run.py
```

Start Next.js in another PowerShell window:

```powershell
yarn dev
```

Open `http://localhost:3000` in your browser. Keep MongoDB and both app processes running.

## Production build and start

```powershell
yarn build
yarn start
```

The production `start` script is intended to run the web app and backend together. Configure the production environment values first and place HTTPS in front of the app. See [FACTORY_SETUP.md](FACTORY_SETUP.md) for factory hosting and security guidance.

## Common issues

- **MongoDB connection fails:** confirm the MongoDB service is running and `MONGO_URL` and `DB_NAME` are correct.
- **Python package import fails:** activate the project virtual environment or run its Python executable explicitly, then install `backend\requirements.txt`.
- **Browser cannot reach the backend:** confirm the web and backend processes are running and the configured base URL and origins match the address opened in the browser.

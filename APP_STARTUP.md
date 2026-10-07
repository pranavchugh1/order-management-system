# App Startup Guide

The commands below are for Windows PowerShell and this project folder. The app uses Next.js, a FastAPI backend, and MongoDB.

## Requirements

- Node.js 20.12 or newer
- Yarn 1.22.22
- Python 3.11 or newer
- MongoDB 5 or newer, running locally or on a reachable server

## First-Time Setup

Open PowerShell in the project folder:

```powershell
Set-Location "C:\Users\prana\Downloads\order system 04oct"
node --version
corepack enable
corepack prepare yarn@1.22.22 --activate
yarn --version
py -3 --version
```

Install the app dependencies and create the Python environment:

```powershell
yarn install --frozen-lockfile
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Create or check the root `.env` file. It must define `MONGO_URL`, `DB_NAME`, `NEXT_PUBLIC_BASE_URL`, `JWT_SECRET`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD`. For local use, set the base URL to `http://localhost:3000`; `MONGO_URL` must point to your running MongoDB. Keep the secret and password private.

## Start For Development

Keep MongoDB running. Open **two PowerShell windows** in the project folder.

In the first window, start the backend:

```powershell
Set-Location "C:\Users\prana\Downloads\order system 04oct"
$env:BACKEND_SOCKET = ""
$env:BACKEND_URL = "http://127.0.0.1:8000"
.\.venv\Scripts\python.exe backend\run.py
```

In the second window, start the website:

```powershell
Set-Location "C:\Users\prana\Downloads\order system 04oct"
$env:BACKEND_SOCKET = ""
$env:BACKEND_URL = "http://127.0.0.1:8000"
yarn dev
```

Open <http://localhost:3000>. Keep both PowerShell windows open. Press `Ctrl+C` in each window to stop its process.

## Production Build And Start

With MongoDB running, use one PowerShell window:

```powershell
Set-Location "C:\Users\prana\Downloads\order system 04oct"
$env:BACKEND_SOCKET = ""
$env:BACKEND_URL = "http://127.0.0.1:8000"
yarn build
yarn start
```

The `start` script launches the backend and the production web server together when no backend is already listening at `BACKEND_URL`. Open <http://localhost:3000>. For production hosting, configure HTTPS and production credentials; see [FACTORY_SETUP.md](FACTORY_SETUP.md).

## Common Fixes

- If MongoDB cannot be reached, start its service and check `MONGO_URL` in `.env`.
- If a Python import fails, run `.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt` from the project folder.
- If port `3000` or `8000` is already in use, stop the other process or change the corresponding port configuration.

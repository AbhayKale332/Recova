# Recova

Recova is a payment-recovery application with a FastAPI backend and a Next.js frontend.

## Prerequisites

- Python 3.12 or newer
- Node.js 20.9 or newer
- npm
- [uv](https://docs.astral.sh/uv/) (recommended for the backend)

## Run locally

Run the backend and frontend in separate terminal windows.

### 1. Start the backend

From the repository root:

```bash
cd Backend
uv sync
uv run uvicorn application.server:app --reload --port 8000
```

The API is available at <http://localhost:8000>. Interactive API documentation is available at <http://localhost:8000/docs>.

If `uv` is not installed, use a virtual environment and `pip` instead:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r Backend/dependencies.txt
cd Backend
python -m uvicorn application.server:app --reload --port 8000
```

The backend uses SQLite by default and creates `Backend/recovery_engine.db` when it starts.

### 2. Start the frontend

In a second terminal, from the repository root:

```bash
cd Frontend
npm ci
cp .env.example .env.local
npm run dev
```

Open the dashboard at <http://localhost:3000>.

The frontend expects the backend at `http://localhost:8000`. To use another backend URL, update `NEXT_PUBLIC_API_BASE` in `Frontend/.env.local`.

## Environment variables

The application runs locally with its built-in defaults. Backend settings can be added to `Backend/.env` when provider integrations are needed, including:

- `GEMINI_API_KEY` for Gemini-powered features
- `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, and `RAZORPAY_WEBHOOK_SECRET` for Razorpay integration
- `ELEVENLABS_API_KEY` for voice features
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_API_KEY_SID`, and `TWILIO_API_KEY_SECRET` for Twilio integration
- `VAPI_API_KEY` for Vapi integration
- `ENCRYPTION_KEY` and `LIVE_MODE` for security and live-mode configuration

Keep secrets out of source control.

## Run tests

From the repository root:

```bash
cd Backend
uv run pytest
```

With the `pip` setup, activate the virtual environment first and run:

```bash
cd Backend
python -m pytest
```

## Production build

To build and run the frontend production bundle:

```bash
cd Frontend
npm run build
npm run start
```

To run the backend without auto-reload:

```bash
cd Backend
uv run uvicorn application.server:app --host 0.0.0.0 --port 8000
```

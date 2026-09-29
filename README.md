# APE Practice Agent

An A2A agent for the APE evaluation toolkit: QA, tool use, image understanding,
web browsing, code execution, and memory across sessions.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

## Run

```bash
python server.py    # A2A server on http://localhost:3000
```
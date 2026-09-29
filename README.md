# APE Practice Agent

An A2A agent for the APE evaluation toolkit: QA, tool use, image understanding,
web browsing, code execution, and memory across sessions.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Create a `.env` file in the project root and define your Anthropic API key:

```bash
ANTHROPIC_API_KEY=your-api-key-here
```


## Run

```bash
python server.py    # A2A server on http://localhost:3000
```
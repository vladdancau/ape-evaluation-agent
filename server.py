from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from agent import MODEL, Agent
from memory import Memory

PORT = 3000
PUBLIC_URL = "http://localhost:3000/"
MEMORY_DB = "memory.db"

agent = Agent(Memory(MEMORY_DB))

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], expose_headers=["*"])

AGENT_CARD = {
    "name": "Practice Agent",
    "description": "Demo purpose agent for APE.",
    "version": "0.1.0",
    "protocolVersion": "0.3.0",
    "capabilities": {"streaming": False, "pushNotifications": False},
    "defaultInputModes": ["text/plain", "image/png", "image/jpeg"],
    "defaultOutputModes": ["text/plain"],
    "skills": [
        {
            "id": "general",
            "name": "General assistant",
            "description": "Answers questions using reasoning and tools.",
            "tags": ["qa", "tools", "vision", "web", "code", "memory"],
        }
    ],
}

@app.get("./well-known/agent-card.json")
async def agent_card(request: Request):
    return {
        **AGENT_CARD, "url": str(request.base_url)
    }


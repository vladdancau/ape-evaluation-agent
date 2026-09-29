import base64, uuid, warnings, httpx, uvicorn

warnings.filterwarnings("ignore", message=".*HTTP_413_REQUEST_ENTITY_TOO_LARGE.*")

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities, AgentCard, AgentSkill, Artifact, DataPart, FilePart, FileWithBytes, Message,
    Part, Task, TaskState, TaskStatus, TextPart,
)
from a2a.utils import new_agent_text_message
from starlette.middleware.cors import CORSMiddleware

from agent import answer

PORT = 3000

AGENT_CARD = AgentCard(
    name="Practice Agent",
    description="Demo agent for APE.",
    url=f"http://localhost:{PORT}/",
    version="0.1.0",
    capabilities=AgentCapabilities(streaming=False),
    default_input_modes=["text/plain", "image/png", "image/jpeg", "image/webp", "image/gif"],
    default_output_modes=["text/plain"],
    skills=[
        AgentSkill(
            id="general",
            name="General assistant",
            description="Answers questions using reasoning and tools.",
            tags=["qa", "tools", "vision", "web", "code", "memory"],
        )
    ],
)


async def _download_as_data_url(uri, mime):
    """Fetch an image URL and inline it, so it works with every model provider."""
    if uri.startswith("data:"):
        return uri
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        r = await client.get(uri)
        r.raise_for_status()
    mime = mime or r.headers.get("content-type", "image/png").split(";")[0]
    return f"data:{mime};base64,{base64.b64encode(r.content).decode()}"


async def message_to_content(message):
    """Text-only messages become a plain string; messages with images become a content list."""
    content = []
    for part in message.parts:
        p = part.root
        if isinstance(p, TextPart):
            content.append({"type": "text", "text": p.text})
        elif isinstance(p, DataPart):
            content.append({"type": "text", "text": str(p.data)})
        elif isinstance(p, FilePart):
            f = p.file
            mime = f.mime_type or ""
            if mime and not mime.startswith("image/"):
                content.append({"type": "text", "text": f"[Attached file {f.name or ''} ({mime}) not supported]"})
            elif isinstance(f, FileWithBytes):
                url = f"data:{mime or 'image/png'};base64,{f.bytes}"
                content.append({"type": "image_url", "image_url": {"url": url}})
            else:
                url = await _download_as_data_url(f.uri, mime or None)
                content.append({"type": "image_url", "image_url": {"url": url}})

    if all(c["type"] == "text" for c in content):
        return "\n".join(c["text"] for c in content)
    return content


def describe(content):
    """Short log line that shows images as placeholders instead of huge base64 strings."""
    if isinstance(content, str):
        return content
    return " ".join(c["text"] if c["type"] == "text" else "[IMAGE]" for c in content)


def completed_task(context, reply):
    """A finished Task with the answer in every place a client might look:
    history (user + agent messages), status.message, and artifacts."""
    agent_msg = new_agent_text_message(reply, context_id=context.context_id, task_id=context.task_id)
    previous = context.current_task.history if context.current_task else [context.message]
    return Task(
        id=context.task_id,
        context_id=context.context_id,
        status=TaskStatus(state=TaskState.completed, message=agent_msg),
        history=[*previous, agent_msg],
        artifacts=[Artifact(artifact_id=str(uuid.uuid4()), name="answer",
                            parts=[Part(root=TextPart(text=reply))])],
    )


class PracticeAgentExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        try:
            content = await message_to_content(context.message)
            print(f"<- {describe(content)[:500]}")
            reply = await answer(content, context.context_id)
        except Exception as e:
            reply = f"Error: {type(e).__name__}: {e}"
        print(f"-> {reply[:500]}\n")
        await event_queue.enqueue_event(completed_task(context, reply))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("cancel not supported")


handler = DefaultRequestHandler(agent_executor=PracticeAgentExecutor(), task_store=InMemoryTaskStore())
app = A2AStarletteApplication(agent_card=AGENT_CARD, http_handler=handler).build()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)

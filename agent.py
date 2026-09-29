import asyncio, json, os, time, litellm

from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from browser import BROWSER_SCHEMAS, BROWSER_TOOLS
from memory import Memory
from tools import TOOL_SCHEMAS, TOOLS

MODEL = os.getenv("MODEL", "anthropic/claude-sonnet-5-5")
TIMEOUT = 60
MAX_STEPS = 30
TIME_BUDGET = 150

memory = Memory(Path(__file__).parent / "memory.db")

RECALL_SCHEMA = {"type": "function", "function": {
    "name": "recall",
    "description": "Search your long-term memory: messages the user sent in previous sessions."
                   "Use when the user refers to something they told you before that isn't shown.",
    "parameters": {"type": "object",
                   "properties": {"query": {"type": "string", "description": "Keywords or numbers to look for."}},
                   "required": ["query"]}}}

ALL_TOOLS = {**TOOLS, **BROWSER_TOOLS, "recall": lambda query: "\n".join(memory.search(query)) or "No matching memories."}
ALL_SCHEMAS = [*TOOL_SCHEMAS, *BROWSER_SCHEMAS, RECALL_SCHEMA]

SYSTEM_PROMPT = """You are a precise, helpful assistant with tools.

Answering:
- Answer the user's question directly and concisely.
- If the question has a single correct answer (a number, name, date, word), state it clearly.
- If the question asks for a number or says "answer with digits", reply with ONLY the number:
  no words, no units, no explanation.
- If the question asks for a specific format (one word, a hash, JSON...), return exactly that.
- For multiple-choice questions, reply with exactly the chosen option as written (or its letter,
  if the question asks for a letter). No explanation.

Images:
- When an image is attached, look at it carefully before answering. Base your answer on what is
  actually visible: objects, animals, text, colors, counts.

Tools:
- Never compute in your head. Use `calculator` for arithmetic and `run_python` for anything
  involving code, algorithms, hashing, primes, loops, or multi-step computation.
- When asked to write or run a program, actually run it with `run_python` and report the real output.
- Use `web_search` then `fetch_url` for current events or facts you are unsure of.
- Base your final answer on the tool results.

Web pages and games:
- For interactive or JavaScript pages (games, buttons, forms), use `browser_open`,
  `browser_click` and `browser_read`. Do not reverse-engineer the site's code.
- Tic-tac-toe: the 9 cells are listed in board order (row by row). After every click,
  read the new board. Choose moves in this order: win now, block the opponent's win,
  take the center, take a corner, take any empty cell. If you lose or draw, click
  "New Game" and play again until you win.
- After winning, report exactly what the task asks for, e.g. the full secret number.

Memory:
- You DO have long-term memory across sessions. Messages the user sent in earlier sessions that
  look relevant are listed below under "Memories from previous sessions".
- When the user refers to something they told you before, answer from those memories.
  If nothing relevant is listed, call `recall` before saying you don't know.
- Never claim you cannot remember previous conversations.
- When the user asks you to remember something, briefly confirm; it is saved automatically."""


def trace(*parts):
    print(f"  [{time.strftime('%H:%M:%S')}]", *parts, flush=True)


def call_tool(name, raw_args):
    try:
        args = json.loads(raw_args or "{}")
        return str(ALL_TOOLS[name](**args))
    except KeyError:
        return f"Error: unknown tool '{name}'"
    except Exception as e:
        return f"Error running {name}: {type(e).__name__}: {e}"


def text_of(content):
    if isinstance(content, str):
        return content
    return " ".join(c["text"] if c["type"] == "text" else "[image]" for c in content)


async def answer(content, context_id):
    text = text_of(content)
    memories = memory.search(text, exclude_context=context_id)
    if memories:
        trace(f"memory: {len(memories)} related message(s) from previous sessions")
    system = SYSTEM_PROMPT + "\n\nMemories from previous sessions:\n" + (
        "\n".join(f"- {m}" for m in memories) if memories else "(none matched this question)")

    messages = [{"role": "system", "content": system},
                *memory.history(context_id),
                {"role": "user", "content": content}]
    memory.add(context_id, "user", text)

    reply = await run_loop(messages)
    memory.add(context_id, "assistant", reply)
    return reply


async def run_loop(messages):
    start = time.time()
    try:
        for step in range(MAX_STEPS):
            out_of_time = time.time() - start > TIME_BUDGET

            response = await litellm.acompletion(
                model=MODEL, messages=messages, timeout=TIMEOUT,
                **({} if out_of_time else {"tools": ALL_SCHEMAS}))
            msg = response.choices[0].message
            tool_calls = msg.tool_calls or []

            if not tool_calls:
                trace(f"step {step}: final answer ({time.time() - start:.1f}s)")
                return (msg.content or "").strip()

            messages.append({"role": "assistant", "content": msg.content,
                             "tool_calls": [{"id": tc.id, "type": "function",
                                             "function": {"name": tc.function.name,
                                                          "arguments": tc.function.arguments}}
                                            for tc in tool_calls]})

            for tc in tool_calls:
                trace(f"step {step}: TOOL {tc.function.name}({tc.function.arguments[:300]})")
                result = await asyncio.to_thread(call_tool, tc.function.name, tc.function.arguments)
                trace(f"          RESULT {result[:300]!r}")
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

        messages.append({"role": "user", "content": "Give your final answer now based on what you have."})
        response = await litellm.acompletion(model=MODEL, messages=messages, timeout=TIMEOUT)
        return (response.choices[0].message.content or "").strip()

    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


if __name__ == "__main__":
    print(f"Model: {MODEL}")
    while True:
        question = input("\nyou> ").strip()
        if question in ("", "quit"):
            break
        print("agent>", asyncio.run(answer(question, context_id="cli")))

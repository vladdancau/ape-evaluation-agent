import ast
import json
import math
import operator
import os
import subprocess
import sys
import tempfile

import httpx
from bs4 import BeautifulSoup

MAX_OUTPUT = 8000
CODE_TIMEOUT = 30


def _truncate(text):
    return text if len(text) <= MAX_OUTPUT else text[:MAX_OUTPUT] + "\n...[truncated]"


def run_python(code):
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "main.py")
        with open(path, "w") as f:
            f.write(code)
        try:
            p = subprocess.run([sys.executable, path], capture_output=True, text=True,
                               timeout=CODE_TIMEOUT, cwd=folder)
        except subprocess.TimeoutExpired:
            return f"Error: code ran longer than {CODE_TIMEOUT}s"
    out = f"exit code: {p.returncode}\nstdout:\n{p.stdout}"
    if p.stderr:
        out += f"\nstderr:\n{p.stderr}"
    return _truncate(out)


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
        ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}
_NAMES = {n: getattr(math, n) for n in dir(math) if not n.startswith("_")} | {"abs": abs, "round": round}


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _NAMES:
        return _NAMES[node.func.id](*[_eval(a) for a in node.args])
    if isinstance(node, ast.Name) and isinstance(_NAMES.get(node.id), float):
        return _NAMES[node.id]
    raise ValueError("only numbers, + - * / // % ** and math functions are allowed")


def calculator(expression):
    try:
        return str(_eval(ast.parse(expression, mode="eval").body))
    except Exception as e:
        return f"Error: {e}"


def web_search(query):
    try:
        from ddgs import DDGS
        results = DDGS().text(query, max_results=5) or []
        return json.dumps([{"title": r.get("title"), "url": r.get("href"), "snippet": r.get("body")}
                           for r in results], ensure_ascii=False, indent=1)
    except Exception as e:
        return f"Search error: {e}"


def fetch_url(url):
    try:
        r = httpx.get(url, timeout=20, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 (compatible; PracticeAgent/0.1)"})
        r.raise_for_status()
        if "html" not in r.headers.get("content-type", ""):
            return _truncate(r.text)
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "nav", "footer"]):
            tag.decompose()
        lines = (line.strip() for line in soup.get_text("\n").splitlines())
        return _truncate("\n".join(line for line in lines if line))
    except Exception as e:
        return f"Fetch error: {e}"


def _schema(name, description, param, param_description):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object",
                       "properties": {param: {"type": "string", "description": param_description}},
                       "required": [param]}}}


TOOL_SCHEMAS = [
    _schema("run_python",
            "Execute Python 3 code and return its stdout/stderr. Use print() to output results. "
            "ALWAYS use this for hashing, encoding, algorithms, loops, primes, dates, string "
            "manipulation, or any multi-step computation. Standard library is available.",
            "code", "Complete Python program; print the final result."),
    _schema("calculator",
            "Evaluate a math expression exactly, e.g. '987654321 * 123456789' or 'sqrt(2)'. "
            "Use for any arithmetic beyond trivial single-digit math.",
            "expression", "Math expression using + - * / // % ** and math functions."),
    _schema("web_search",
            "Search the web. Returns titles, URLs and snippets. Use for current events or facts you are unsure of.",
            "query", "Search query."),
    _schema("fetch_url",
            "Fetch a web page and return its readable text. Use after web_search, or when given a URL.",
            "url", "Full URL including https://"),
]

TOOLS = {"run_python": run_python, "calculator": calculator,
         "web_search": web_search, "fetch_url": fetch_url}

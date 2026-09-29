import os, time

from concurrent.futures import ThreadPoolExecutor
from playwright.sync_api import sync_playwright

HEADLESS = os.getenv("BROWSER_HEADLESS", "1") != "0"
SETTLE_SECONDS = 1.5

_thread = ThreadPoolExecutor(max_workers=1, thread_name_prefix="browser")
_state: dict = {}

_SNAPSHOT_JS = r"""() => {
  const selector = 'a, button, input, select, textarea, [onclick], [role=button], .cell, [data-cell], [data-index], td';
  const items = [];
  let n = 0;
  document.querySelectorAll('[data-agent-id]').forEach(el => el.removeAttribute('data-agent-id'));
  document.querySelectorAll(selector).forEach(el => {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    if (!r.width || !r.height || s.visibility === 'hidden' || s.display === 'none') return;
    el.setAttribute('data-agent-id', ++n);
    const cls = typeof el.className === 'string' && el.className.trim()
      ? '.' + el.className.trim().split(/\s+/).join('.') : '';
    const text = (el.innerText || el.value || '').trim().replace(/\s+/g, ' ').slice(0, 60);
    items.push(`[${n}] <${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}${cls}> "${text}"`);
  });
  return {url: location.href, title: document.title,
          text: document.body.innerText.trim().slice(0, 4000), items};
}"""


def _page():
    page = _state.get("page")
    if page is None or page.is_closed():
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=HEADLESS)
        _state.update(pw=pw, browser=browser, page=browser.new_page())
    return _state["page"]


def _snapshot():
    snap = _page().evaluate(_SNAPSHOT_JS)
    return (f"URL: {snap['url']}\nTitle: {snap['title']}\n\n"
            f"Visible text:\n{snap['text']}\n\n"
            "Interactive elements (pass the number to browser_click):\n" + "\n".join(snap["items"]))


def _run(fn, *args):
    try:
        return _thread.submit(fn, *args).result(timeout=60)
    except Exception as e:
        return f"Browser error: {type(e).__name__}: {e}"


def _open(url):
    page = _page()
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass
    return _snapshot()


def _click(element):
    _page().click(f'[data-agent-id="{int(element)}"]', timeout=5000)
    time.sleep(SETTLE_SECONDS)
    return _snapshot()


def browser_open(url):
    return _run(_open, url)


def browser_click(element):
    return _run(_click, element)


def browser_read():
    return _run(_snapshot)


BROWSER_TOOLS = {"browser_open": browser_open, "browser_click": browser_click, "browser_read": browser_read}

BROWSER_SCHEMAS = [
    {"type": "function", "function": {
        "name": "browser_open",
        "description": "Open a URL in a real browser (runs JavaScript). Returns the visible text and a "
                       "numbered list of clickable elements. Use this instead of fetch_url for "
                       "interactive pages, games, or pages built by JavaScript.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "browser_click",
        "description": "Click an element by its number from the latest snapshot, wait for the page to "
                       "react, and return the updated page. Element numbers can change after each "
                       "click, so always use the numbers from the most recent result.",
        "parameters": {"type": "object", "properties": {"element": {"type": "integer"}},
                       "required": ["element"]}}},
    {"type": "function", "function": {
        "name": "browser_read",
        "description": "Return the current page's visible text and clickable elements without doing anything.",
        "parameters": {"type": "object", "properties": {}}}},
]

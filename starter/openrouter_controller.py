"""Controller adapter: real LLM via OpenRouter chat completions with tools.

Implements Controller.decide from agentic.py using NATIVE tool calling: the
model either calls the `search` tool (mapped to {'action': 'search', ...}) or
writes a final answer whose [chunk-id] inline markers become the citation
list (run_agent re-validates every id against the packed context). An answer
without any valid citation marker is normalized to an abstention by the
agent loop, which is exactly the intended no-evidence behavior.

Stateless per call: the message list is rebuilt from (question, history), so
decide() mirrors what run_agent passes and nothing else is remembered.
Config: OPENROUTER_MODEL (default openai/gpt-4o-mini), OPENROUTER_API_KEY.

HTTP uses http.client with the host PINNED to the module constant: there is
no caller-supplied URL anywhere in this module.
"""
from __future__ import annotations

import http.client
import json
import os
import re
import time
from typing import Any

from day7_env import load_env, require

API_HOST = 'openrouter.ai'
API_PATH = '/api/v1/chat/completions'
TIMEOUT_SECONDS = 90
CITATION_RE = re.compile(r'\[([0-9a-f]{16})\]')

SYSTEM_PROMPT = (
    'You are a retrieval agent answering questions about the book "Think Python, 2nd '
    'Edition" (English corpus, chapters 1-5). You have one tool: search(query).\n'
    'Protocol:\n'
    '1. Always start by calling search with a short, focused query. English queries '
    'match this corpus best; you may try a second, differently-worded query when the '
    'first results are weak.\n'
    '2. Search results are evidence chunks formatted as [chunk-id | source | page N] '
    'followed by the chunk text.\n'
    '3. When you can answer, write the final answer IN VIETNAMESE, grounded only in '
    'the chunks. Cite the chunk used inline using its exact [chunk-id] marker, e.g. '
    ' "... [737ff12306987fd6]". Keep answers concise (2-4 sentences).\n'
    '4. If after searching the chunks do not contain sufficient evidence, reply '
    'exactly: Không đủ bằng chứng để trả lời.\n'
    'Never use outside knowledge. Never invent or alter chunk ids; copy them exactly '
    'from the chunks you cite.')

SEARCH_TOOL = {
    'type': 'function',
    'function': {
        'name': 'search',
        'description': 'Search the indexed book corpus for evidence chunks',
        'parameters': {
            'type': 'object',
            'properties': {'query': {'type': 'string',
                                     'description': 'Short search query, English preferred'}},
            'required': ['query'],
        },
    },
}


def _post_chat(payload: dict) -> dict:
    """POST to the pinned OpenRouter endpoint; raise sanitized errors."""
    api_key = require('OPENROUTER_API_KEY')
    if any(c in api_key for c in '\r\n'):
        raise RuntimeError('OPENROUTER_API_KEY chứa ký tự xuống dòng; giá trị header không hợp lệ')
    body = json.dumps(payload).encode('utf-8')
    connection = http.client.HTTPSConnection(API_HOST, timeout=TIMEOUT_SECONDS)
    started = time.perf_counter()
    try:
        connection.request('POST', API_PATH, body=body, headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'})
        response = connection.getresponse()
        raw = response.read()
    except OSError as exc:
        raise RuntimeError('OpenRouter chat lỗi transport (details suppressed)') from exc
    finally:
        connection.close()
    _post_chat.last_elapsed_ms = (time.perf_counter() - started) * 1000
    if response.status >= 400:
        snippet = raw.decode('utf-8', 'replace')[:300]
        raise RuntimeError(f'OpenRouter chat lỗi HTTP {response.status}: {snippet}')
    try:
        return json.loads(raw.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError('phản hồi OpenRouter không phải JSON hợp lệ') from exc


class OpenRouterController:
    """Real-model Controller over OpenRouter; records usage per call."""

    def __init__(self, model: str | None = None, temperature: float = 0.0,
                 system_prompt: str | None = None) -> None:
        load_env()
        self.model = model or os.environ.get('OPENROUTER_MODEL', 'openai/gpt-4o-mini')
        self.temperature = temperature
        self.system_prompt = system_prompt or SYSTEM_PROMPT
        self.usage_totals = {'prompt_tokens': 0, 'completion_tokens': 0, 'calls': 0}
        self.latencies_ms: list[float] = []

    def _messages(self, question: str, history: list[dict[str, Any]]) -> list[dict]:
        messages: list[dict] = [{'role': 'system', 'content': self.system_prompt},
                                {'role': 'user', 'content': question}]
        for record in history:
            queries = record.get('queries') or []
            if queries:
                messages.append({'role': 'assistant', 'content': None, 'tool_calls': [
                    {'id': f'call_{i}', 'type': 'function',
                     'function': {'name': 'search', 'arguments': json.dumps({'query': q})}}
                    for i, q in enumerate(queries)]})
                # one tool response per tool_call id (providers reject dangling ids);
                # run_agent keeps one cumulative context, sent for each call
                for i in range(len(queries)):
                    messages.append({'role': 'tool', 'tool_call_id': f'call_{i}',
                                     'content': record.get('context') or '(no results)'})
            else:
                messages.append({'role': 'assistant', 'content': '(searching...)'})
                messages.append({'role': 'tool', 'tool_call_id': 'call_0',
                                 'content': record.get('context') or '(no results)'})
        return messages

    def _complete(self, messages: list[dict]) -> dict:
        body = _post_chat({'model': self.model, 'messages': messages,
                           'tools': [SEARCH_TOOL], 'tool_choice': 'auto',
                           'temperature': self.temperature})
        self.latencies_ms.append(_post_chat.last_elapsed_ms)
        usage = body.get('usage') or {}
        self.usage_totals['prompt_tokens'] += usage.get('prompt_tokens', 0) or 0
        self.usage_totals['completion_tokens'] += usage.get('completion_tokens', 0) or 0
        self.usage_totals['calls'] += 1
        choices = body.get('choices') or []
        if not choices or not choices[0].get('message'):
            raise RuntimeError('phản hồi OpenRouter không có message')
        return choices[0]['message']

    def decide(self, question: str, history: list[dict[str, Any]]) -> dict[str, Any]:
        message = self._complete(self._messages(question, history))
        tool_calls = message.get('tool_calls') or []
        if tool_calls:
            call = tool_calls[0]['function']
            if call.get('name') != 'search':
                raise ValueError(f'model gọi tool lạ: {call.get("name")!r}')
            arguments = json.loads(call.get('arguments') or '{}')
            query = arguments.get('query')
            if not isinstance(query, str) or not query.strip():
                raise ValueError('search query từ model rỗng hoặc không hợp lệ')
            return {'action': 'search', 'query': query.strip()}
        answer = (message.get('content') or '').strip()
        if not answer:
            raise ValueError('model không trả tool call lẫn answer text')
        citations = list(dict.fromkeys(CITATION_RE.findall(answer)))
        return {'action': 'answer', 'answer': answer, 'citations': citations}

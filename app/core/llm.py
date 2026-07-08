"""
LLM Client — 无状态函数式调用
============================================================
chat(config, system_prompt, user_prompt) -> str
支持 OpenAI 和 Anthropic 两种协议，根据 base_url 自动判断。
"""
import json
import urllib.request
import urllib.error


def chat(config: dict, system_prompt: str, user_prompt: str,
         temperature: float = None) -> str:
    """调用 LLM，自动选择 OpenAI 或 Anthropic 协议"""

    api_key = config["api_key"]
    base_url = config["base_url"]
    model = config["model"]
    temp = temperature if temperature is not None else config["temperature"]

    if not api_key:
        raise RuntimeError("未配置 LLM_API_KEY，请在 .env 中设置")

    if "/anthropic" in base_url:
        return _chat_anthropic(api_key, base_url, model, system_prompt, user_prompt, temp)
    else:
        return _chat_openai(api_key, base_url, model, system_prompt, user_prompt, temp)


def _chat_openai(api_key, base_url, model, system, user, temp):
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temp,
        "max_tokens": 8192,
    }).encode()

    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"] or ""


def _chat_anthropic(api_key, base_url, model, system, user, temp):
    body = json.dumps({
        "model": model,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "max_tokens": 8192,
        "temperature": temp,
    }).encode()

    req = urllib.request.Request(
        f"{base_url}/v1/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            content = data.get("content", [])
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            return texts[0] if texts else ""
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:500]
        raise RuntimeError(f"API {e.code}: {body}") from e


def chat_stream(config: dict, system_prompt: str, user_prompt: str,
                temperature: float = None, on_chunk=None) -> str:
    """流式调用 LLM，每收到一段文本就回调 on_chunk(text)。
    自动选择 OpenAI 或 Anthropic 协议。"""

    api_key = config["api_key"]
    base_url = config["base_url"]
    model = config["model"]
    temp = temperature if temperature is not None else config["temperature"]

    if "/anthropic" in base_url:
        return _chat_stream_anthropic(api_key, base_url, model, system_prompt, user_prompt, temp, on_chunk)
    else:
        return _chat_stream_openai(api_key, base_url, model, system_prompt, user_prompt, temp, on_chunk)


def _chat_stream_openai(api_key, base_url, model, system, user, temp, on_chunk):
    """OpenAI 兼容流式（支持 DeepSeek, OpenAI, 等）"""
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": 8192,
        "temperature": temp,
        "stream": True,
    }).encode()

    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    full_text = []
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            for line_bytes in resp:
                line = line_bytes.decode("utf-8", errors="replace").strip()
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    continue
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                delta = data.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content", "")
                # DeepSeek 的 reasoning_content（跳过）
                if delta.get("reasoning_content"):
                    continue
                if content:
                    full_text.append(content)
                    if on_chunk:
                        on_chunk(content)
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()[:500]
        raise RuntimeError(f"API {e.code}: {body_text}") from e

    return "".join(full_text)


def _chat_stream_anthropic(api_key, base_url, model, system, user, temp, on_chunk):
    """Anthropic 流式"""
    body = json.dumps({
        "model": model,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "max_tokens": 8192,
        "temperature": temp,
        "stream": True,
    }).encode()

    req = urllib.request.Request(
        f"{base_url}/v1/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    full_text = []
    in_thinking = False
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            for line_bytes in resp:
                line = line_bytes.decode("utf-8", errors="replace").strip()
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                t = data.get("type", "")
                if t == "content_block_start":
                    in_thinking = data.get("content_block", {}).get("type") == "thinking"
                    continue
                if t == "content_block_stop":
                    in_thinking = False
                    continue
                if in_thinking:
                    continue

                delta = data.get("delta", {})
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    if text:
                        full_text.append(text)
                        if on_chunk:
                            on_chunk(text)
                if t == "message_stop":
                    break
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()[:500]
        raise RuntimeError(f"API {e.code}: {body_text}") from e

    return "".join(full_text)


# ── SSE 流辅助 ────────────────────────────────────────
import asyncio as _asyncio
import queue as _queue
import threading as _threading


async def sse_chat(config: dict, system_prompt: str, user_prompt: str):
    """流式调用 LLM，yield SSE 事件字符串。完成后可通过 .full_text 获取全文。
    
    Usage:
        gen = sse_chat(cfg, sys, usr)
        async for event in gen:
            yield event
        full_text = gen.full_text  # 流结束后的完整文本
    """
    q = _queue.Queue()

    def _run():
        try:
            chat_stream(config, system_prompt, user_prompt,
                        on_chunk=lambda t: q.put(("chunk", t)))
            q.put(("done", None))
        except Exception as e:
            q.put(("error", str(e)))

    t = _threading.Thread(target=_run)
    t.start()
    full_text = []

    while True:
        try:
            kind, data = q.get(timeout=0.1)
            if kind == "chunk":
                full_text.append(data)
                yield f"data: {json.dumps({'type': 'chunk', 'text': data}, ensure_ascii=False)}\n\n"
            elif kind == "done":
                break
            elif kind == "error":
                yield f"data: {json.dumps({'type': 'error', 'message': data}, ensure_ascii=False)}\n\n"
                t.join()
                return
        except _queue.Empty:
            await _asyncio.sleep(0.05)

    t.join()
    sse_chat.full_text = "".join(full_text)

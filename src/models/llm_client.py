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
        "max_tokens": 4096,
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
        "max_tokens": 4096,
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
    """流式调用 LLM，每收到一段文本就回调 on_chunk(text)"""
    api_key = config["api_key"]
    base_url = config["base_url"]
    model = config["model"]
    temp = temperature if temperature is not None else config["temperature"]

    body = json.dumps({
        "model": model,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
        "max_tokens": 4096,
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
                try: data = json.loads(data_str)
                except json.JSONDecodeError: continue

                t = data.get("type","")
                if t == "content_block_start":
                    in_thinking = data.get("content_block",{}).get("type")=="thinking"
                    continue
                if t == "content_block_stop":
                    in_thinking = False; continue
                if in_thinking: continue

                delta = data.get("delta", {})
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    if text:
                        full_text.append(text)
                        if on_chunk: on_chunk(text)
                if t == "message_stop": break
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:500]
        raise RuntimeError(f"API {e.code}: {body}") from e

    return "".join(full_text)

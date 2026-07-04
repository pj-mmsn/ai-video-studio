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

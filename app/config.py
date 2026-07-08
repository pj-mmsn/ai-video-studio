"""
配置加载 — 函数式，默认缓存，可选强制刷新
============================================================
首次调用读 .env 并缓存，后续调用返回缓存副本。
需要刷新时调用 reload_config() 或 load_config(use_cache=False)。
"""
import os
from dotenv import load_dotenv

_config_cache = None  # 模块级缓存


def load_config(use_cache: bool = True) -> dict:
    """加载配置，返回 dict。默认使用缓存，避免重复读 .env"""
    global _config_cache
    if use_cache and _config_cache is not None:
        return _config_cache.copy()

    load_dotenv(override=True)  # override=True: .env 覆盖已有环境变量

    _config_cache = {
        # LLM
        "api_key": os.getenv("LLM_API_KEY", ""),
        "base_url": os.getenv("LLM_BASE_URL", "https://api.deepseek.com/anthropic"),
        "model": os.getenv("LLM_MODEL", "deepseek-v4-pro"),
        "model_light": os.getenv("LLM_MODEL_LIGHT", "deepseek-v4-flash"),
        "temperature": float(os.getenv("LLM_TEMPERATURE", "0.7")),
        "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "4096")),

        # 图像
        "image_api_key": os.getenv("IMAGE_API_KEY", ""),
        "image_base_url": os.getenv("IMAGE_BASE_URL", "https://api.openai.com/v1"),
        "image_model": os.getenv("IMAGE_MODEL", "dall-e-3"),

        # 视频
        "video_api_key": os.getenv("VIDEO_API_KEY", ""),
        "video_base_url": os.getenv("VIDEO_BASE_URL", ""),
        "video_model": os.getenv("VIDEO_MODEL", ""),

        # 输出
        "output_dir": os.getenv("OUTPUT_DIR", "output"),
    }
    return _config_cache.copy()


def reload_config() -> dict:
    """强制重新加载配置（忽略缓存）"""
    return load_config(use_cache=False)

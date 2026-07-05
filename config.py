"""
配置加载 — 函数式，每次调用重新读 .env
============================================================
不缓存，不 dataclass。每次 load_config() 返回当前 env 值。
"""
import os
from dotenv import load_dotenv


def load_config() -> dict:
    """加载配置，返回 dict。每次调用重新读环境变量"""
    load_dotenv(override=True)  # override=True: .env 覆盖已有环境变量

    return {
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

"""
统一日志系统
============================================================
替代全项目 print() 调用，支持：
- 控制台输出（彩色）
- 文件持久化（output/logs/）
- DEBUG/INFO/WARN/ERROR 四级
"""
import logging
import sys
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent.parent / "output" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 全局 logger
logger = logging.getLogger("video_studio")
logger.setLevel(logging.DEBUG)

# 控制台 handler（INFO 以上）
console = logging.StreamHandler(sys.stdout)
console.setLevel(logging.INFO)
console.setFormatter(logging.Formatter(
    "%(message)s"  # 控制台简洁
))
logger.addHandler(console)

# 文件 handler（DEBUG 以上，全量日志）
file_handler = logging.FileHandler(
    LOG_DIR / "studio.log", encoding="utf-8"
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
))
logger.addHandler(file_handler)

# 便捷别名
debug = logger.debug
info = logger.info
warn = logger.warning
error = logger.error

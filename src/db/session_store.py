"""
Redis 会话层 — Agent 的工作记忆
============================================================
SQLite = 硬盘（全部数据）
Redis = 内存（当前写作会话的热数据）

流程:
  1. 开启会话 → 从 SQL 加载上下文到 Redis
  2. 写作 → 读写 Redis（毫秒级）
  3. 上下文满了 → 旧数据 flush 到 SQL，Redis 只保留热数据
  4. 结束会话 → flush 全部到 SQL，清理 Redis
"""
import json
import os
from typing import Optional

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_DB = int(os.environ.get("REDIS_DB", "0"))


class SessionStore:
    """Redis 会话存储——Agent 的工作记忆

    如果没有 Redis，降级为内存 dict（单次会话有效，重启丢失）。
    """

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.prefix = f"novel:{project_id}"
        self._redis = None
        self._fallback = {}  # 降级内存存储

        try:
            import redis
            self._redis = redis.Redis(
                host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB,
                decode_responses=True, socket_connect_timeout=2
            )
            self._redis.ping()
        except Exception:
            self._redis = None

    def _k(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    @property
    def available(self) -> bool:
        return self._redis is not None

    # ================================================================
    # 上下文管理（核心）
    # ================================================================

    def load_context(self, sql_context: dict) -> None:
        """从 SQL 加载上下文到 Redis（开启会话时调用）

        sql_context 来自 NovelRepository.get_writing_context()
        """
        ctx = {
            "current_node": str(sql_context.get("current_node_id", "")),
            "context_text": sql_context.get("context_text", ""),
            "characters": json.dumps(sql_context.get("characters", [])),
            "threads": json.dumps(sql_context.get("threads", [])),
            "rules": json.dumps(sql_context.get("rules", [])),
            "recent_summaries": json.dumps(sql_context.get("recent_summaries", [])),
            "token_estimate": str(sql_context.get("token_estimate", 0)),
        }
        self._hset("context", ctx)

    def get_context(self) -> dict:
        """获取当前上下文（LLM 调用前读取）"""
        data = self._hgetall("context")
        return {
            "context_text": data.get("context_text", ""),
            "characters": json.loads(data.get("characters", "[]")),
            "threads": json.loads(data.get("threads", "[]")),
            "rules": json.loads(data.get("rules", "[]")),
            "recent_summaries": json.loads(data.get("recent_summaries", "[]")),
            "token_estimate": int(data.get("token_estimate", "0")),
        }

    def update_after_write(self, section_id: int, summary: str,
                           new_characters: list = None,
                           resolved_threads: list = None) -> None:
        """写完一节后更新上下文"""
        # 追加摘要到最近列表（只保留最近5个）
        summaries = json.loads(self._hget("context", "recent_summaries") or "[]")
        summaries.append(summary)
        summaries = summaries[-5:]
        self._hset("context", {"recent_summaries": json.dumps(summaries)})

        # 更新角色
        if new_characters:
            for c in new_characters:
                self._hset("characters", {c.get("name", ""): json.dumps(c)})

        # 标记已解决的伏笔
        if resolved_threads:
            for tid in resolved_threads:
                self._srem("active_threads", str(tid))

        # 递增位置
        self._incr("sections_written")

    # ================================================================
    # 会话管理
    # ================================================================

    def start_session(self) -> dict:
        """开始新的写作会话"""
        self._set("session_active", "1")
        self._set("session_started", str(__import__('time').time()))
        self._del("sections_written")
        return {"status": "active", "redis": self.available}

    def end_session(self) -> dict:
        """结束会话——返回需要 flush 到 SQL 的数据"""
        data = {
            "context": self.get_context(),
            "sections_written": int(self._get("sections_written") or "0"),
            "characters": self._hgetall("characters"),
        }
        self._flush()  # 清理 Redis
        return data

    def is_active(self) -> bool:
        return self._get("session_active") == "1"

    # ================================================================
    # 超限检测
    # ================================================================

    def check_overflow(self, max_tokens: int = 6000) -> bool:
        """检查上下文是否超限，需要 flush 旧数据到 SQL"""
        ctx = self.get_context()
        return ctx["token_estimate"] > max_tokens

    def trim_context(self) -> dict:
        """裁剪上下文——把最旧的数据打包返回（调用方负责写入 SQL）"""
        summaries = json.loads(self._hget("context", "recent_summaries") or "[]")
        if len(summaries) <= 2:
            return {}

        # 取出最旧的摘要
        old = summaries.pop(0)
        self._hset("context", {"recent_summaries": json.dumps(summaries)})
        return {"flushed_summary": old, "remaining_count": len(summaries)}

    # ================================================================
    # 底层操作（兼容 Redis + dict fallback）
    # ================================================================

    def _get(self, key: str) -> Optional[str]:
        if self._redis:
            return self._redis.get(self._k(key))
        return self._fallback.get(self._k(key))

    def _set(self, key: str, value: str):
        if self._redis:
            self._redis.set(self._k(key), value)
        else:
            self._fallback[self._k(key)] = value

    def _del(self, key: str):
        if self._redis:
            self._redis.delete(self._k(key))
        else:
            self._fallback.pop(self._k(key), None)

    def _incr(self, key: str) -> int:
        if self._redis:
            return self._redis.incr(self._k(key))
        v = int(self._fallback.get(self._k(key), "0")) + 1
        self._fallback[self._k(key)] = str(v)
        return v

    def _hset(self, key: str, mapping: dict):
        if self._redis:
            self._redis.hset(self._k(key), mapping=mapping)
        else:
            existing = json.loads(self._fallback.get(self._k(key), "{}"))
            existing.update(mapping)
            self._fallback[self._k(key)] = json.dumps(existing)

    def _hget(self, key: str, field: str) -> Optional[str]:
        if self._redis:
            return self._redis.hget(self._k(key), field)
        data = json.loads(self._fallback.get(self._k(key), "{}"))
        return data.get(field)

    def _hgetall(self, key: str) -> dict:
        if self._redis:
            return self._redis.hgetall(self._k(key))
        return json.loads(self._fallback.get(self._k(key), "{}"))

    def _srem(self, key: str, member: str):
        if self._redis:
            self._redis.srem(self._k(key), member)
        else:
            s = set(json.loads(self._fallback.get(self._k(key), "[]")))
            s.discard(member)
            self._fallback[self._k(key)] = json.dumps(list(s))

    def _flush(self):
        if self._redis:
            keys = self._redis.keys(f"{self.prefix}:*")
            if keys:
                self._redis.delete(*keys)
        else:
            self._fallback.clear()

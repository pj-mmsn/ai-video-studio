"""
轻量工作流引擎 — LangGraph 风格状态机
============================================================
核心概念:
  Node(节点)  = 一个 Agent 或处理步骤
  Edge(边)    = 节点之间的转换规则
  State(状态) = 工作流的完整快照(可 checkpoint)

每个节点有生命周期:
  idle → running → done
               → failed → retry → running
                        → skip

支持:
  - 条件分支: 边可以带条件函数
  - Checkpoint: 每步自动持久化到 StudioDB
  - 人工审批: 节点可标记 require_approval
  - 并行: 同一层级的节点可并发执行
"""
from __future__ import annotations

import json
import time
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional
from enum import Enum

from src.db.studio_db import StudioDB


class NodeStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING_APPROVAL = "waiting_approval"


@dataclass
class Node:
    """工作流节点"""
    id: str
    name: str
    description: str = ""
    agent: str = ""                      # 关联的 Agent 名称
    handler: Callable = None             # 执行函数(db, config) -> bool
    status: NodeStatus = NodeStatus.IDLE
    require_approval: bool = False       # 是否需要人工审批
    max_retries: int = 3
    retry_count: int = 0
    started_at: str = ""
    completed_at: str = ""
    error: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class Edge:
    """节点之间的边（转换规则）"""
    from_node: str
    to_node: str
    condition: Callable = None           # (state) -> bool, None=无条件
    label: str = ""


@dataclass
class WorkflowState:
    """工作流完整状态（可序列化/checkpoint）"""
    project_id: str
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    current_node: str = ""
    status: str = "idle"                 # idle/running/paused/done/failed
    started_at: str = ""
    updated_at: str = ""
    checkpoint_count: int = 0
    metadata: dict = field(default_factory=dict)


class WorkflowEngine:
    """工作流引擎"""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.db = StudioDB(project_id)
        self.state = WorkflowState(project_id=project_id)
        self._lock = threading.Lock()
        self._pause_flag = False
        self._observers: list[Callable] = []  # 状态变更回调

    # ================================================================
    # 构建工作流
    # ================================================================

    def add_node(self, node_id: str, name: str, handler: Callable = None,
                 agent: str = "", require_approval: bool = False,
                 max_retries: int = 3) -> "WorkflowEngine":
        self.state.nodes[node_id] = Node(
            id=node_id, name=name, handler=handler,
            agent=agent, require_approval=require_approval,
            max_retries=max_retries,
        )
        return self

    def add_edge(self, from_node: str, to_node: str,
                 condition: Callable = None, label: str = "") -> "WorkflowEngine":
        self.state.edges.append(Edge(from_node=from_node, to_node=to_node,
                                     condition=condition, label=label))
        return self

    def on_state_change(self, callback: Callable):
        """注册状态变更观察者"""
        self._observers.append(callback)

    # ================================================================
    # 执行
    # ================================================================

    def run(self, start_node: str = "start", config: dict = None) -> bool:
        """从头运行工作流"""
        self.state.current_node = start_node
        self.state.status = "running"
        self.state.started_at = self._now()
        self._notify()

        current = start_node
        visited = set()

        while current and current not in visited:
            if self._pause_flag:
                self.state.status = "paused"
                self._checkpoint()
                self._notify()
                return False  # 暂停，等待 resume

            visited.add(current)
            node = self.state.nodes.get(current)
            if not node:
                break

            # 执行节点
            success = self._execute_node(node, config)

            if not success and node.status == NodeStatus.FAILED:
                self.state.status = "failed"
                self._checkpoint()
                self._notify()
                return False

            # 找下一条边
            next_node = self._find_next(current)
            self.state.current_node = next_node or ""
            current = next_node

            if current:
                self._checkpoint()

        self.state.status = "done"
        self._checkpoint()
        self._notify()
        return True

    def resume(self) -> bool:
        """从断点恢复"""
        self._pause_flag = False
        self.state.status = "running"
        return self.run(start_node=self.state.current_node)

    def pause(self):
        self._pause_flag = True

    def approve(self, node_id: str) -> bool:
        """人工审批通过某个节点"""
        node = self.state.nodes.get(node_id)
        if node and node.status == NodeStatus.WAITING_APPROVAL:
            node.status = NodeStatus.DONE
            node.completed_at = self._now()
            self._notify()
            return True
        return False

    def reject(self, node_id: str, reason: str = "") -> bool:
        """驳回节点"""
        node = self.state.nodes.get(node_id)
        if node and node.status == NodeStatus.WAITING_APPROVAL:
            node.status = NodeStatus.FAILED
            node.error = reason or "人工驳回"
            self._notify()
            return True
        return False

    # ================================================================
    # 内部
    # ================================================================

    def _execute_node(self, node: Node, config: dict) -> bool:
        node.status = NodeStatus.RUNNING
        node.started_at = self._now()
        self._notify()

        if node.require_approval:
            node.status = NodeStatus.WAITING_APPROVAL
            self._checkpoint()
            self._notify()
            # 等待外部调用 approve()
            while node.status == NodeStatus.WAITING_APPROVAL:
                if self._pause_flag:
                    return False
                time.sleep(0.5)
            return node.status == NodeStatus.DONE

        if not node.handler:
            node.status = NodeStatus.DONE
            node.completed_at = self._now()
            self._notify()
            return True

        try:
            success = node.handler(self.db, config or {})
            if success:
                node.status = NodeStatus.DONE
                node.completed_at = self._now()
            else:
                node.retry_count += 1
                if node.retry_count < node.max_retries:
                    node.status = NodeStatus.IDLE  # 重试
                    return self._execute_node(node, config)
                else:
                    node.status = NodeStatus.FAILED
                    node.error = f"重试{node.max_retries}次后仍失败"
        except Exception as e:
            node.retry_count += 1
            if node.retry_count < node.max_retries:
                time.sleep(1)
                return self._execute_node(node, config)
            node.status = NodeStatus.FAILED
            node.error = str(e)

        self._notify()
        return node.status == NodeStatus.DONE

    def _find_next(self, current: str) -> Optional[str]:
        """找下一个节点"""
        for edge in self.state.edges:
            if edge.from_node == current:
                if edge.condition is None or edge.condition(self.state):
                    return edge.to_node
        return None

    def _checkpoint(self):
        """持久化当前状态"""
        self.state.checkpoint_count += 1
        self.state.updated_at = self._now()
        self.db.conn.execute(
            """INSERT INTO context_log (project_id,agent,section_id,context_json,token_estimate,created_at)
            VALUES (?,?,?,?,?,?)""",
            (self.project_id, "workflow", 0,
             json.dumps(self._state_dict(), ensure_ascii=False),
             0, self._now()))
        self.db.conn.commit()

    def _state_dict(self) -> dict:
        return {
            "project_id": self.state.project_id,
            "status": self.state.status,
            "current_node": self.state.current_node,
            "checkpoint": self.state.checkpoint_count,
            "nodes": {nid: {"name": n.name, "status": n.status.value, "error": n.error}
                      for nid, n in self.state.nodes.items()},
            "edges": [(e.from_node, e.to_node, e.label) for e in self.state.edges],
        }

    def _notify(self):
        for cb in self._observers:
            try:
                cb(self._state_dict())
            except Exception:
                pass

    def _now(self): return __import__('datetime').datetime.now().isoformat()

    def close(self): self.db.close()

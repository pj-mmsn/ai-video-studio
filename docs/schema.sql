-- AI 小说家 数据库 DDL
-- 位置: output/novels/<项目ID>/novel.db

CREATE TABLE IF NOT EXISTS novels (
    id TEXT PRIMARY KEY,
    title TEXT DEFAULT '',
    genre TEXT DEFAULT '',
    premise TEXT DEFAULT '',
    status TEXT DEFAULT 'draft',
    total_words INTEGER DEFAULT 0,
    created_at TEXT DEFAULT '',
    updated_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS outline_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    novel_id TEXT,
    parent_id INTEGER,
    level TEXT,                        -- volume | chapter | section
    sort_order INTEGER,
    title TEXT DEFAULT '',
    summary TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    FOREIGN KEY(parent_id) REFERENCES outline_nodes(id)
);

CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    novel_id TEXT,
    outline_node_id INTEGER,
    content TEXT DEFAULT '',
    word_count INTEGER DEFAULT 0,
    summary TEXT DEFAULT '',
    version INTEGER DEFAULT 1,
    created_at TEXT DEFAULT '',
    updated_at TEXT DEFAULT '',
    FOREIGN KEY(outline_node_id) REFERENCES outline_nodes(id)
);

CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    novel_id TEXT,
    name TEXT DEFAULT '',
    role TEXT DEFAULT '',              -- 主角 | 配角 | 反派
    traits TEXT DEFAULT '',            -- 外貌性格
    arc TEXT DEFAULT '',               -- 角色弧线(成长方向)
    notes TEXT DEFAULT '',
    first_appearance_section INTEGER,
    updated_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS character_scenes (
    character_id INTEGER,
    section_id INTEGER,
    role_in_scene TEXT DEFAULT '',
    PRIMARY KEY(character_id, section_id)
);

CREATE TABLE IF NOT EXISTS world_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    novel_id TEXT,
    category TEXT DEFAULT '',          -- 灵气体系 | 地理 | 历史 | 势力 | ...
    key TEXT DEFAULT '',
    value TEXT DEFAULT '',
    source_section INTEGER,
    tags TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS plot_threads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    novel_id TEXT,
    description TEXT DEFAULT '',
    status TEXT DEFAULT 'open',        -- open | resolved
    introduced_section INTEGER,
    resolved_section INTEGER,
    tags TEXT DEFAULT '',
    priority INTEGER DEFAULT 5         -- 1-10 数字越大越重要
);

CREATE TABLE IF NOT EXISTS story_bible (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT,
    category TEXT DEFAULT '',          -- character | world_rule | plot_point
    key TEXT DEFAULT '',
    value TEXT DEFAULT '',
    source_scene INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS context_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    novel_id TEXT,
    section_id INTEGER,
    context_json TEXT DEFAULT '',      -- 本次注入的上下文JSON快照
    token_estimate INTEGER DEFAULT 0,  -- 估算token数
    created_at TEXT DEFAULT ''
);

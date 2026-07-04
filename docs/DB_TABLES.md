# 数据库表结构

> 数据库位置: `output/novels/<项目ID>/novel.db` | 引擎: SQLite

---

## 表结构

### novels — 项目元数据
| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | 项目ID |
| title | TEXT | 书名 |
| genre | TEXT | 类型(玄幻/科幻/都市...) |
| premise | TEXT | 一句话梗概 |
| status | TEXT | 状态(draft/in_progress/done) |
| total_words | INTEGER | 总字数 |
| created_at | TEXT | 创建时间 |
| updated_at | TEXT | 更新时间 |

### outline_nodes — 分层大纲(树形结构)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增 |
| novel_id | TEXT FK | 项目ID |
| parent_id | INTEGER | 父节点ID(卷的parent=null) |
| level | TEXT | 层级(volume/chapter/section) |
| sort_order | INTEGER | 排序 |
| title | TEXT | 标题 |
| summary | TEXT | 概要 |
| status | TEXT | pending/done |

### sections — 已写正文
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增 |
| novel_id | TEXT FK | 项目ID |
| outline_node_id | INTEGER FK | 关联大纲节点 |
| content | TEXT | 正文全文 |
| word_count | INTEGER | 字数 |
| summary | TEXT | 摘要 |
| version | INTEGER | 版本号(修改递增) |
| created_at | TEXT | 创建时间 |
| updated_at | TEXT | 更新时间 |

### characters — 角色档案
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增 |
| novel_id | TEXT FK | 项目ID |
| name | TEXT | 角色名 |
| role | TEXT | 主角/配角/反派 |
| traits | TEXT | 外貌性格特征 |
| arc | TEXT | 角色弧线(成长/黑化/...) |
| notes | TEXT | 补充说明 |
| first_appearance_section | INTEGER | 首次出场章节 |
| updated_at | TEXT | 更新时间 |

### character_scenes — 角色出场记录
| 字段 | 类型 | 说明 |
|------|------|------|
| character_id | INTEGER PK | 角色ID |
| section_id | INTEGER PK | 章节ID |
| role_in_scene | TEXT | 本场景中角色状态 |

### world_rules — 世界观规则
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增 |
| novel_id | TEXT FK | 项目ID |
| category | TEXT | 分类(灵气体系/地理/历史...) |
| key | TEXT | 规则名 |
| value | TEXT | 规则值 |
| source_section | INTEGER | 来源章节 |
| tags | TEXT | 标签(逗号分隔) |

### plot_threads — 伏笔/剧情线
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增 |
| novel_id | TEXT FK | 项目ID |
| description | TEXT | 伏笔描述 |
| status | TEXT | open/resolved |
| introduced_section | INTEGER | 引入章节 |
| resolved_section | INTEGER | 解决章节 |
| tags | TEXT | 标签 |
| priority | INTEGER | 优先级(1-10) |

### story_bible — 故事圣经(通用键值)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增 |
| project_id | TEXT | 项目ID |
| category | TEXT | 分类(character/world_rule/plot_point) |
| key | TEXT | 键 |
| value | TEXT | 值 |
| source_scene | INTEGER | 来源 |
| updated_at | TEXT | 更新时间 |

### context_logs — 上下文日志(调试)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增 |
| novel_id | TEXT FK | 项目ID |
| section_id | INTEGER | 章节ID |
| context_json | TEXT | 注入的上下文JSON快照 |
| token_estimate | INTEGER | 估算token数 |
| created_at | TEXT | 创建时间 |

---

## 常用查询

```sql
-- 总进度
SELECT status, total_words FROM novels;

-- 开了多少伏笔没收
SELECT COUNT(*) FROM plot_threads WHERE status='open';

-- 哪些角色还没出场
SELECT name FROM characters WHERE first_appearance_section IS NULL;

-- 某节注入了多少上下文
SELECT section_id, token_estimate, created_at FROM context_logs ORDER BY created_at DESC LIMIT 10;

-- 已写完的章节
SELECT os.title, s.word_count, s.created_at
FROM sections s JOIN outline_nodes os ON s.outline_node_id = os.id
ORDER BY s.created_at DESC;
```

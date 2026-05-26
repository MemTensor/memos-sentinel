# MemOS Sentinel

**MemOS PR & Issues Orchestrator Agent** — 为 [MemTensor/MemOS](https://github.com/MemTensor/MemOS) 提供智能化的 Issue/PR 全生命周期管理与自动开发能力。

> *An AI-powered orchestrator that manages issues, reviews PRs, and auto-fixes bugs for the MemOS project.*

---

## 架构概览 / Architecture

```
                    ┌─────────────────────────────────┐
                    │       GitHub Webhook / Cron      │
                    └──────────────┬──────────────────┘
                                   │
                    ┌──────────────▼──────────────────┐
                    │     Router (四档分发)             │
                    │  fast / light / full / dev       │
                    └──┬───────┬────────┬────────┬────┘
                       │       │        │        │
              ┌────────▼┐ ┌───▼────┐ ┌─▼─────┐ ┌▼──────────┐
              │ FastPath │ │ Light  │ │ Full  │ │ DevAgent  │
              │ (规则)   │ │ Agent  │ │ Agent │ │ (ai-task) │
              │ 0 LLM   │ │ 3-step │ │10-step│ │ 15-step   │
              └──────────┘ └────────┘ └───────┘ └───────────┘
                       │       │        │        │
              ┌────────▼───────▼────────▼────────▼────┐
              │         21 Tools (GitHub API)          │
              │   9 Read + 6 Write + 6 Dev (git ops)  │
              └───────────────────────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
       ┌──────▼──────┐    ┌───────▼──────┐    ┌───────▼──────┐
       │  DingTalk    │    │   SQLite     │    │  LangSmith   │
       │  通知+审批   │    │  审计日志     │    │  可观测性     │
       └─────────────┘    └──────────────┘    └──────────────┘
```

## 核心能力 / Features

### 已实现 (Implemented)

| 模块 | 能力 | 文件 |
|------|------|------|
| 四档路由 | 根据事件类型自动分发到 fast/light/full/dev 路径 | `src/agent/router.py` |
| 标签分类 | 三维标签体系 (type × module × priority)，规则 + LLM 分类 | `src/labels/classifier.py` |
| 4 模块体系 | `mod:plugin` / `mod:memos` / `mod:docs` / `mod:infra` | `src/labels/schema.py` |
| 并发锁 | 防止同一 issue/PR 被重复处理，TTL 5min | `src/agent/concurrency.py` |
| 错误重试 | 指数退避重试，可配置最大次数和延迟 | `src/agent/retry.py` |
| 重复检测 | 标题/内容相似度匹配，自动标记 duplicate | `src/agent/duplicate_detector.py` |
| 回复模板 | 8 种场景英文模板 + LLM fallback | `config/templates.yaml` |
| Human Gate | 危险操作需人工审批 (close/approve) | `src/agent/human_gate.py` |
| 钉钉通知 | 审批卡片 + 状态推送 | `src/notify/dingtalk.py` |
| Web 审批页 | 一键 approve/reject 页面 | `src/web/confirm.py` |
| 数据库 | AuditLog + PendingAction + TaskQueue | `src/store/models.py` |
| 定时任务 | 每日 stale 扫描 + 日报 | `src/scheduler/cron.py` |
| Merge 策略 | squash 默认, require CI pass + 1 人 approve | `config/settings.yaml` |
| Base 分支 | main 默认, regression 走 release/* | `src/agent/dev_agent.py` |

### 待开发 (TODO)

| 优先级 | 能力 | 说明 |
|--------|------|------|
| P0 | GitHub API 真实接入 | 21 个 Tool 当前为 placeholder，需接 PyGithub |
| P0 | Phase 1 批量扫描 CLI | 扫描 MemOS 186 issues + 30 PRs，输出分类报告 |
| P1 | LangGraph StateGraph | 构建真正的状态图，绑定 Tool，实现 ReAct 循环 |
| P1 | GitHub App 注册 | 创建 App，配置权限，获取 JWT 认证 |
| P1 | LLM 分类 fallback | 规则匹配失败时调用 Claude 进行语义分类 |
| P1 | PR 深度审查 | Opus 4 读 diff + 上下文，生成结构化 review |
| P2 | Dev Agent git 操作 | 真实 clone/branch/edit/commit/push 实现 |
| P2 | CI 监控 + 重试 | 轮询 CI 状态，失败后分析日志并自动修复 |
| P2 | LangSmith 集成 | 全链路 trace，token 统计，延迟监控 |
| P2 | Dashboard 完善 | 日报可视化，处理统计，标签分布图 |
| P3 | 多仓库支持 | 配置多个 target repo |
| P3 | GitHub App Marketplace | 打包为可安装的 App |

---

## 技术栈 / Tech Stack

- **Language**: Python 3.11+
- **Framework**: FastAPI + LangGraph
- **LLM**: Claude Sonnet 4 (Router) + Claude Opus 4 (Review/Code)
- **Observability**: LangSmith
- **Database**: SQLite (async via SQLAlchemy)
- **Notifications**: DingTalk Robot
- **Deployment**: Docker + docker-compose

---

## 快速开始 / Quick Start

```bash
# Clone
git clone https://github.com/MemTensor/memos-sentinel.git
cd memos-sentinel

# 配置
cp .env.example .env
# 编辑 .env 填入 API keys

# 安装依赖
pip install -e ".[dev]"

# 启动 (dry-run 模式)
uvicorn src.main:app --reload --port 8000

# 或 Docker
docker compose up -d
```

## 配置 / Configuration

| 文件 | 用途 |
|------|------|
| `.env` | 密钥和环境变量 |
| `config/settings.yaml` | Agent 行为、merge 策略、重试、并发 |
| `config/labels.yaml` | 标签体系定义 + 迁移映射 |
| `config/templates.yaml` | 英文回复模板 |
| `config/repo_context.yaml` | MemOS 仓库结构 (给 Agent 上下文) |

---

## 项目结构 / Project Structure

```
src/
├── main.py              # FastAPI 入口
├── webhook.py           # Webhook handler
├── agent/               # Agent 核心逻辑
│   ├── router.py        # 四档路由
│   ├── fast_path.py     # 规则引擎
│   ├── light_agent.py   # 轻量 Agent
│   ├── full_agent.py    # 完整 Agent (PR review)
│   ├── dev_agent.py     # 开发 Agent (ai-task)
│   ├── human_gate.py    # 人工审批
│   ├── concurrency.py   # 并发锁
│   ├── retry.py         # 重试逻辑
│   └── ...
├── tools/               # 21 个 GitHub 工具
├── labels/              # 标签分类系统
├── llm/                 # 双模型 client
├── notify/              # 钉钉通知
├── web/                 # 审批页 + Dashboard
├── store/               # 数据库
└── scheduler/           # 定时任务
```

---

## License

MIT

---

## English Summary

**MemOS Sentinel** is an AI orchestrator agent that manages the full lifecycle of issues and pull requests for the MemOS project. It provides:

- **Automated triage**: Three-dimensional label classification (type × module × priority)
- **PR review**: Deep code review powered by Claude Opus 4
- **Auto-fix**: Triggered by `ai-task` label — analyzes bugs, writes fixes, creates draft PRs
- **Human-in-the-loop**: Dangerous actions require approval via DingTalk + web confirmation
- **Observability**: Full audit trail in SQLite + LangSmith tracing

The agent routes events through four complexity tiers (fast → light → full → dev) to optimize cost and latency, only invoking expensive models when needed.

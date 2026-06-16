<div align="center">

# 🏨 Revenue Manager Agent
### Grand Harbour Hotel · Ireland · 2026

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Railway-6366f1?style=for-the-badge&logo=railway)](https://otel-revenue-agent-production.up.railway.app)
[![Python](https://img.shields.io/badge/Python-3.13-3776ab?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![LangChain](https://img.shields.io/badge/LangChain-Deep%20Agents-1c7a4a?style=for-the-badge)](https://langchain.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Supabase](https://img.shields.io/badge/Supabase-West%20EU-3ecf8e?style=for-the-badge&logo=supabase&logoColor=white)](https://supabase.com)

**An AI Revenue Manager that answers natural-language questions for a Hotel General Manager — using live reservation data, LangChain Deep Agents, and a deliberately designed tool + skill layer.**

[**→ Live Demo**](https://otel-revenue-agent-production.up.railway.app) · Built for the [Otel AI Build Challenge](https://github.com/otel-ai/otel-build-challenge)

</div>

---

## 💬 What it does

Ask it anything a Revenue Manager would say in a morning GM briefing:

| Question | What happens |
|----------|-------------|
| *"What revenue is on the books by month?"* | Calls `get_otb_summary`, returns monthly OTB with drivers |
| *"Which segments are driving August 2026?"* | Calls `get_segment_mix`, identifies top 3 with share % |
| *"Are we too dependent on OTA?"* | Loads `ota_concentration` skill, applies 35% threshold |
| *"What changed in the last 7 days?"* | Calls `get_pickup_delta` with London midnight UTC boundaries |
| *"How much group business do we have?"* | Calls `get_block_vs_transient_mix`, flags concentration risk |

---

## 🏗️ Architecture

```
Playwright ETL → Supabase Postgres → Semantic Views → 5 Tools → Deep Agent → FastAPI → Railway
```

| Layer | Technology | Detail |
|-------|-----------|--------|
| 🕷️ Scraper | Playwright | Async, paginated list → detail drill-in, 254 reservations |
| 🗄️ Database | Supabase Postgres | West EU Ireland, 523 stay rows |
| 🔭 Semantic views | SQL | `vw_stay_night_base`, `vw_segment_stay_night` |
| 🤖 Agent | LangChain Deep Agents | `create_deep_agent()`, GPT-4o mini |
| 🧠 Memory | LangGraph MemorySaver | Multi-turn GM conversation |
| 🌐 API | FastAPI | `/health`, `/chat`, `/` with basic auth |
| 🚀 Deploy | Railway | Auto-deploy from GitHub |

---

## 🛠️ Five Tools

> No `run_sql` tool. Correctness is enforced in the tool layer — grain, filters, and date logic are baked in, not improvised by the model.

| Tool | Purpose |
|------|---------|
| `get_otb_summary` | Revenue on the books by month — Posted, non-cancelled rows via `vw_stay_night_base` |
| `get_segment_mix` | Market segment breakdown with **effective** macro groups (not static lookup) |
| `get_pickup_delta` | New bookings in a window — Europe/London midnight converted to UTC |
| `get_as_of_otb` | Point-in-time OTB snapshot — **HITL gated** (requires GM approval) |
| `get_block_vs_transient_mix` | Group vs transient split with top company concentration |

---

## 📚 Six Skills (otel-rm-v2)

> Skills encode the **judgment** of an experienced revenue manager — not just metric definitions, but thresholds, traps, and recommended actions.

| Skill | What it encodes |
|-------|----------------|
| `CHALLENGE_SKILL.md` | Core persona, tool routing matrix, adversarial guardrails, cross-skill triggers |
| `otb_summary.md` | OTB interpretation, implied occupancy thresholds, multi-month pacing guidance |
| `pickup_pace.md` | London midnight UTC boundary logic, pace signals, net pickup alerts |
| `ota_concentration.md` | OTA share thresholds (>35% = risk), channel mix targets, commission cost context |
| `block_concentration.md` | Group concentration risk (>40% = warning), company concentration, single-block risk |
| `cancellation_analysis.md` | Cancellation rate benchmarks, revenue at risk flags, policy recommendations |

---

## ⚙️ Agent Engineering

```python
agent = create_deep_agent(
    model=ChatOpenAI(model="gpt-4o-mini"),
    tools=[get_otb_summary, get_segment_mix, get_pickup_delta, get_as_of_otb, get_block_vs_transient_mix],
    system_prompt=SYSTEM_PROMPT,          # sharp revenue-manager persona
    skills=skill_paths,                    # 6 skills via progressive disclosure
    checkpointer=MemorySaver(),            # multi-turn GM conversation
    interrupt_on={"get_as_of_otb": True}, # HITL gate
    subagents={"mix_analyst": mix_spec},  # specialist for segment/block analysis
)
```

---

## 📁 Project Structure

```
├── agent/                  # Deep Agent, subagent, system prompt
├── api/                    # FastAPI backend + chat UI (tool/skill visibility)
├── etl/
│   ├── scraper.py          # Playwright scraper
│   ├── loader.py           # Idempotent ETL loader
│   ├── SCRAPE_MANIFEST.json
│   └── LOAD_PROOF.json     # Verified against /verify on scrape day
├── skills/                 # 6 skill files (otel-rm-v2)
├── sql/                    # Semantic views
├── tests/                  # test_etl, test_tools, test_skills, test_agent
├── tools/
│   ├── hotel_tools.py      # 5 required tools
│   └── METRIC_DEFINITIONS.md
├── scripts/
│   └── compute_load_fingerprint.py
├── ARCHITECTURE.md         # Skill→tool routing matrix + HITL docs
└── ATTESTATION.md
```

---

## 🚀 Run Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Add: OPENAI_API_KEY, DATABASE_URL

# Run ETL
python etl/run_etl.py

# CLI agent
python agent/agent.py

# Web UI
uvicorn api.main:app --reload
# → http://localhost:8000
```

---

## 🔍 Health Endpoint

```bash
curl https://otel-revenue-agent-production.up.railway.app/health -u otel:revenue2026
```

```json
{
  "status": "healthy",
  "db_fingerprint": "3388ad54...",
  "dataset_revision": "2026.06.12.2",
  "row_hash": "3388ad54...",
  "financial_status_posted_only_rows": 475
}
```

---

## 📊 Dataset

| Metric | Value |
|--------|-------|
| Total reservations | 254 |
| Total stay rows | 523 |
| Posted stay rows | 475 |
| Cancelled reservations | 20 |
| Dataset revision | 2026.06.12.2 |
| Hotel inventory | 98 rooms (52 KS + 20 TB + 26 EX) |

---

<div align="center">

*Built by **Kritheshvar Vinothkumar** · [LinkedIn](https://linkedin.com/in/krithesh-analyst) · [GitHub](https://github.com/krithesh19) · [Portfolio](https://kritheshportfolio.netlify.app)*

</div>

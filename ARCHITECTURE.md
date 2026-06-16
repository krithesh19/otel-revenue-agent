# Architecture — Revenue Manager Agent

## Stack overview

| Layer | Technology |
|-------|-----------|
| Scraper | Playwright (async, paginated list → detail drill-in) |
| Database | Supabase Postgres (West EU — Ireland) |
| Semantic views | `vw_stay_night_base`, `vw_segment_stay_night` |
| Agent harness | LangChain Deep Agents (`create_deep_agent`) |
| LLM | GPT-4o mini (OpenAI) |
| Memory | `MemorySaver` checkpointer — multi-turn GM session |
| API | FastAPI — `/health`, `/POST /chat`, `GET /` |
| Deploy | Railway (auto-deploy from GitHub) |

---

## Skill → Tool routing matrix

| GM question type | Skill loaded | Tool called |
|-----------------|-------------|-------------|
| Revenue on the books by month | `otb_summary.md` | `get_otb_summary` |
| Segment / market mix | `otb_summary.md` | `get_segment_mix` |
| OTA dependency / concentration | `ota_concentration.md` | `get_segment_mix` |
| Booking pace / pickup / what changed | `pickup_pace.md` | `get_pickup_delta` |
| Point-in-time historical OTB | `otb_summary.md` | `get_as_of_otb` ⚠️ HITL |
| Group vs transient / block mix | `block_concentration.md` | `get_block_vs_transient_mix` |
| Cancellation impact | `cancellation_analysis.md` | `get_otb_summary(exclude_cancelled=False)` |
| Challenge capability check | `CHALLENGE_SKILL.md` | any |

---

## Human-in-the-loop (HITL)

`get_as_of_otb` is gated behind approval via `interrupt_on={"get_as_of_otb": True}` in `create_deep_agent()`.

**Why:** Point-in-time OTB rebuilds a historical snapshot by replaying `create_datetime` and `cancellation_datetime` boundaries. An incorrect `as_of_utc` value silently produces a misleading comparison. HITL forces the GM to confirm the target date before the agent executes the query.

---

## Memory and multi-turn conversation

`MemorySaver` is passed as the `checkpointer` to `create_deep_agent()`. Each GM session uses a stable `thread_id` (derived from the session cookie) so the agent retains context across questions — e.g. "drilling into July" after asking "what's on the books by month?" does not require re-stating the month.

---

## Subagent routing

Segment-mix and block-mix analysis is routed to a focused subagent via the Deep Agents `task` tool. The primary agent delegates to the subagent with a scoped prompt, receives structured output, and synthesises the GM-facing narrative. This keeps the primary agent's context clean and prevents tool-call bleed between revenue and mix workstreams.

---

## Tool design principle

No `run_sql` tool is exposed to the model. All five tools encode business rules in Python:

- **Grain enforcement** — queries use `COUNT(DISTINCT reservation_id)` for reservations, `SUM(number_of_spaces)` for room nights
- **Default OTB filters** — `vw_stay_night_base` excludes `Cancelled` and `Provisional` rows at view level
- **Date correctness** — `stay_date` for OTB, `create_datetime` (UTC) for pickup, Europe/London midnight for window boundaries
- **Effective macro groups** — `vw_segment_stay_night` joins `market_macro_group_history` on `stay_date` overlap, not the static `macro_group` column

---

## Skills design

6 skills, each with YAML frontmatter (`name`, `description`, `version: otel-rm-v2`):

| Skill file | Type | Judgment encoded |
|-----------|------|-----------------|
| `otb_summary.md` | Metric + judgment | OTB filters, row vs reservation distinction, monthly pacing thresholds |
| `pickup_pace.md` | Judgment | Booking window boundaries (London midnight/UTC), pace vs prior week comparison |
| `ota_concentration.md` | Judgment + threshold | OTA share >35% = concentration risk; recommended rate parity action |
| `block_concentration.md` | Judgment + threshold | Block share >50% room nights = displacement risk; recommended transient protection |
| `cancellation_analysis.md` | Judgment | Cancellation revenue impact, wash factor interpretation |
| `CHALLENGE_SKILL.md` | Meta | Pack version `otel-rm-v2`, adversarial guardrails, answer-style rules |

---

## Answer style (system prompt)

The agent is instructed to answer like a sharp revenue manager in a morning GM briefing:
1. Lead with the headline number or trend
2. Name the top 1–2 drivers
3. Flag any risk or opportunity
4. End with a clear recommended action

Numbers-only or dashboard-read responses are explicitly prohibited in the system prompt.

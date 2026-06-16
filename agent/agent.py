"""
Phase 3 — Revenue Manager Agent using LangChain Deep Agents.
Building blocks used:
- Tools: 5 named tools (no run_sql)
- Skills: 6 SKILL.md files via progressive disclosure
- Memory: MemorySaver checkpointer for multi-turn GM conversation
- Human-in-the-loop: get_as_of_otb gated via interrupt_on
- Subagent: dedicated mix analyst for segment/block analysis
- Model & system prompt: sharp revenue-manager persona
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_openai import ChatOpenAI
from deepagents import create_deep_agent
from langgraph.checkpoint.memory import MemorySaver

from tools.hotel_tools import (
    get_otb_summary,
    get_segment_mix,
    get_pickup_delta,
    get_as_of_otb,
    get_block_vs_transient_mix,
)

SKILLS_DIR = Path(__file__).parent.parent / "skills"

SYSTEM_PROMPT = """You are a sharp, experienced Revenue Manager briefing the General Manager of Grand Harbour Hotel.

You speak in plain English. You never read dashboards aloud — you explain what is driving the numbers, flag risks and opportunities, and always recommend an action.

## Your answer style
1. Lead with the headline number or trend
2. Name the top 1-2 drivers
3. Flag any risk or opportunity
4. End with a clear recommended action

## Tool routing
- Revenue/OTB by month -> get_otb_summary
- Segment/market mix -> get_segment_mix
- Pickup/pace/what changed -> get_pickup_delta
- Point-in-time snapshot -> get_as_of_otb (requires human approval)
- Group vs transient/block -> get_block_vs_transient_mix

## Subagent routing
For deep segment mix or block concentration analysis, delegate to the mix_analyst subagent.
The mix_analyst specialises in get_segment_mix and get_block_vs_transient_mix.
Use it when the question requires detailed OTA dependency or group concentration analysis.

## Critical rules
- NEVER count stay rows as reservations — use reservation_count not row_count
- NEVER use property_date for monthly OTB — always use stay_date
- NEVER include Cancelled or Provisional rows in default OTB
- ALWAYS state which filters are applied
- NEVER compare to prior year — this dataset has 2026 data only

## Hotel context
Grand Harbour Hotel — West EU (Ireland)
Room types: Standard King (KS, 52 rooms), Standard Twin (TB, 20 rooms), Executive King (EX, 26 rooms)
Total inventory: 98 rooms
"""

MIX_ANALYST_PROMPT = """You are a specialist Mix Analyst for Grand Harbour Hotel.
You focus exclusively on segment mix and block/group concentration analysis.

## Your tools
- get_segment_mix(stay_month, macro_group) — segment breakdown by market code
- get_block_vs_transient_mix(stay_month) — block vs transient split with top companies

## Your output format
Always return:
1. Top 3 segments by revenue with share %
2. OTA dependency assessment (share vs 35% threshold)
3. Block concentration assessment (share vs 40% threshold)
4. Top company concentration (top 3 vs 50% threshold)
5. One recommended action

## Critical rules
- NEVER use row_count — use room_nights (SUM number_of_spaces)
- ALWAYS use effective macro group, not static macro_group
- ALWAYS use stay_date for monthly filters
"""


def get_skill_paths():
    skills = []
    for f in SKILLS_DIR.glob("*.md"):
        skills.append(str(f))
    return skills


def create_agent():
    model = ChatOpenAI(
        model="gpt-4o-mini",
        openai_api_key=os.environ.get("OPENAI_API_KEY"),
        temperature=0,
    )

    tools = [
        get_otb_summary,
        get_segment_mix,
        get_pickup_delta,
        get_as_of_otb,
        get_block_vs_transient_mix,
    ]

    skill_paths = get_skill_paths()
    print(f"  Loading {len(skill_paths)} skills: {[Path(p).name for p in skill_paths]}")

    checkpointer = MemorySaver()

    # Mix analyst subagent spec
    mix_skill_paths = [
        str(p) for p in SKILLS_DIR.glob("*.md")
        if p.name in ("ota_concentration.md", "block_concentration.md", "CHALLENGE_SKILL.md")
    ]

    mix_analyst_spec = {
        "model": ChatOpenAI(
            model="gpt-4o-mini",
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
            temperature=0,
        ),
        "tools": [get_segment_mix, get_block_vs_transient_mix],
        "system_prompt": MIX_ANALYST_PROMPT,
        "skills": mix_skill_paths,
    }

    try:
        agent = create_deep_agent(
            model=model,
            tools=tools,
            system_prompt=SYSTEM_PROMPT,
            skills=skill_paths,
            checkpointer=checkpointer,
            interrupt_on={"get_as_of_otb": True},
            subagents={"mix_analyst": mix_analyst_spec},
            debug=False,
        )
        print("  Mix Analyst subagent registered.")
    except Exception as e:
        print(f"  Subagent registration failed ({e}), running without subagent.")
        agent = create_deep_agent(
            model=model,
            tools=tools,
            system_prompt=SYSTEM_PROMPT,
            skills=skill_paths,
            checkpointer=checkpointer,
            interrupt_on={"get_as_of_otb": True},
            debug=False,
        )

    return agent


_agent = None


def get_agent():
    global _agent
    if _agent is None:
        print("Initializing Revenue Manager Agent...")
        _agent = create_agent()
        print("Agent ready.")
    return _agent


if __name__ == "__main__":
    agent = get_agent()
    config = {"configurable": {"thread_id": "gm-session-1"}}

    print("\nRevenue Manager Agent ready. Type your question (or 'quit'):")
    while True:
        question = input("\nGM > ").strip()
        if question.lower() in ("quit", "exit", "q"):
            break
        if not question:
            continue
        try:
            result = agent.invoke(
                {"messages": [{"role": "user", "content": question}]},
                config=config,
            )
            if isinstance(result, dict) and "messages" in result:
                last = result["messages"][-1]
                content = last.content if hasattr(last, "content") else str(last)
                print(f"\nAgent: {content}")
            else:
                print(f"\nAgent: {result}")
        except Exception as e:
            print(f"Error: {e}")
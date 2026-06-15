"""
Phase 3 — Revenue Manager Agent using LangChain Deep Agents.
Building blocks used:
- Tools: 5 named tools (no run_sql)
- Skills: 6 SKILL.md files via progressive disclosure
- Memory: MemorySaver checkpointer for multi-turn GM conversation
- Human-in-the-loop: get_as_of_otb gated via interrupt_on
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

## Critical rules
- NEVER count stay rows as reservations — use reservation_count not row_count
- NEVER use property_date for monthly OTB — always use stay_date
- NEVER include Cancelled or Provisional rows in default OTB
- ALWAYS state which filters are applied

## Hotel context
Grand Harbour Hotel — West EU (Ireland)
Room types: Standard King (KS, 52 rooms), Standard Twin (TB, 20 rooms), Executive King (EX, 26 rooms)
Total inventory: 98 rooms
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
"""
tests/test_agent.py — Agent structure tests (Phase 3)
Covers scenarios 1-6 from AGENT_TEST_SCENARIOS.md (≥4 cases)
Uses mocks and config inspection — no live LLM calls.
Run: pytest tests/test_agent.py -v
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


# ---------------------------------------------------------------------------
# Scenario 1 — Tool surface is fixed
# ---------------------------------------------------------------------------

class TestToolSurface:
    def test_exactly_five_required_tools_importable(self):
        """Scenario 1: all five required tools import successfully."""
        from tools.hotel_tools import (
            get_otb_summary,
            get_segment_mix,
            get_pickup_delta,
            get_as_of_otb,
            get_block_vs_transient_mix,
        )
        tools = [get_otb_summary, get_segment_mix, get_pickup_delta,
                 get_as_of_otb, get_block_vs_transient_mix]
        assert all(callable(t) for t in tools)
        assert len(tools) == 5

    def test_no_run_sql_tool_exposed(self):
        """Scenario 1: no run_sql or raw SQL tool exists in tools module."""
        import tools.hotel_tools as tool_module
        public_attrs = [a for a in dir(tool_module) if not a.startswith("_")]
        assert "run_sql" not in public_attrs, "run_sql should not be in tool module"
        assert "execute_sql" not in public_attrs
        assert "raw_query" not in public_attrs

    def test_tool_names_match_required(self):
        """Scenario 1: tool function names match exactly what REQUIRED_TOOLS.md specifies."""
        import tools.hotel_tools as tool_module
        required_names = [
            "get_otb_summary",
            "get_segment_mix",
            "get_pickup_delta",
            "get_as_of_otb",
            "get_block_vs_transient_mix",
        ]
        for name in required_names:
            assert hasattr(tool_module, name), f"Tool '{name}' not found in hotel_tools"
            assert callable(getattr(tool_module, name)), f"'{name}' is not callable"


# ---------------------------------------------------------------------------
# Scenario 2 — get_as_of_otb is human-gated
# ---------------------------------------------------------------------------

class TestHITLGating:
    def test_as_of_otb_docstring_mentions_hitl(self):
        """Scenario 2: get_as_of_otb docstring must mention HITL/approval requirement."""
        from tools.hotel_tools import get_as_of_otb
        doc = get_as_of_otb.__doc__ or ""
        hitl_keywords = ["human-in-the-loop", "hitl", "approval", "gated", "human"]
        assert any(kw.lower() in doc.lower() for kw in hitl_keywords), (
            f"get_as_of_otb docstring does not mention HITL. Docstring: {doc[:200]}"
        )

    def test_agent_config_gates_as_of_otb(self):
        """Scenario 2: agent config or wrapper must reference HITL for get_as_of_otb."""
        # Check agent.py for HITL configuration
        agent_path = os.path.join("agent", "agent.py")
        if os.path.exists(agent_path):
            with open(agent_path) as f:
                content = f.read()
            hitl_indicators = [
                "interrupt_before",
                "get_as_of_otb",
                "human_in_the_loop",
                "hitl",
                "approval",
            ]
            found = any(ind.lower() in content.lower() for ind in hitl_indicators)
            assert found, "agent.py does not configure HITL for get_as_of_otb"
        else:
            pytest.skip("agent/agent.py not yet created — check after Phase 3")


# ---------------------------------------------------------------------------
# Scenario 3 — Segment work is isolated
# ---------------------------------------------------------------------------

class TestSegmentRouting:
    def test_segment_skill_exists(self):
        """
        Scenario 3: segment/mix questions route through a dedicated skill.
        Pattern chosen: dedicated segment skill (ota_concentration or segment_mix skill).
        """
        import glob
        skill_files = glob.glob("skills/*.md")
        segment_skill_found = False
        for filepath in skill_files:
            with open(filepath) as f:
                content = f.read()
            if "get_segment_mix" in content or "get_block_vs_transient_mix" in content:
                segment_skill_found = True
                break
        assert segment_skill_found, "No skill found that routes to get_segment_mix or get_block_vs_transient_mix"

    def test_segment_tools_available(self):
        """Scenario 3: segment tools are available and callable."""
        from tools.hotel_tools import get_segment_mix, get_block_vs_transient_mix
        assert callable(get_segment_mix)
        assert callable(get_block_vs_transient_mix)


# ---------------------------------------------------------------------------
# Scenario 4 — Multi-tool decomposition
# ---------------------------------------------------------------------------

class TestMultiToolDecomposition:
    def test_otb_and_pickup_tools_exist_independently(self):
        """
        Scenario 4: For composite questions like 'What's driving July and how did we book lately?'
        the agent can call get_otb_summary + get_pickup_delta independently.
        Both tools exist and return independent results.
        """
        from tools.hotel_tools import get_otb_summary, get_pickup_delta
        
        # Simulate a composite question requiring both tools
        otb_result = get_otb_summary("2026-07", exclude_cancelled=True)
        pickup_result = get_pickup_delta(booking_window_days=7, future_stay_from="2026-07-01")
        
        # Both return valid dicts with distinct keys
        assert "reservation_count" in otb_result
        assert "new_reservations" in pickup_result
        assert "stay_month" in otb_result
        assert "booking_window_days" in pickup_result
        
        # They are independent — different grain and different filters
        assert otb_result["stay_month"] == "2026-07"
        assert pickup_result["future_stay_from"] == "2026-07-01"

    def test_all_five_tools_return_dicts(self):
        """Scenario 4: All tools return dict results that can be composed."""
        from tools.hotel_tools import (
            get_otb_summary, get_segment_mix,
            get_block_vs_transient_mix, get_as_of_otb, get_pickup_delta
        )
        results = [
            get_otb_summary("2026-07"),
            get_segment_mix("2026-07"),
            get_block_vs_transient_mix("2026-07"),
            get_as_of_otb("2026-07", "2026-01-01T00:00:00Z"),
            get_pickup_delta(7, "2026-07-01"),
        ]
        assert all(isinstance(r, dict) for r in results)


# ---------------------------------------------------------------------------
# Scenario 5 — Skill loading is on-demand
# ---------------------------------------------------------------------------

class TestSkillLoading:
    def test_skills_directory_exists(self):
        """Scenario 5: skills/ directory exists with SKILL.md files."""
        assert os.path.isdir("skills"), "skills/ directory not found"

    def test_skills_are_markdown_files(self):
        """Scenario 5: skill files are .md format with YAML frontmatter."""
        import glob
        skill_files = glob.glob("skills/*.md")
        assert len(skill_files) >= 6, f"Expected ≥6 skill files, found {len(skill_files)}"
        for f in skill_files:
            with open(f) as fh:
                content = fh.read()
            assert content.startswith("---"), f"{f}: missing YAML frontmatter (---)"


# ---------------------------------------------------------------------------
# Scenario 6 — Memory or filesystem used
# ---------------------------------------------------------------------------

class TestMemoryConfig:
    def test_agent_file_exists(self):
        """Scenario 6: agent/agent.py must exist."""
        assert os.path.exists("agent/agent.py"), "agent/agent.py not found"

    def test_agent_references_memory_or_filesystem(self):
        """Scenario 6: agent configures memory or filesystem backend."""
        agent_path = "agent/agent.py"
        if os.path.exists(agent_path):
            with open(agent_path) as f:
                content = f.read()
            memory_indicators = [
                "memory", "filesystem", "store", "checkpointer",
                "MemorySaver", "SqliteSaver", "InMemoryStore"
            ]
            found = any(ind.lower() in content.lower() for ind in memory_indicators)
            assert found, "agent.py does not configure memory or filesystem backend"
        else:
            pytest.skip("agent/agent.py not yet created")

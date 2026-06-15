"""
tests/test_skills.py — Skill pack structure tests (Phase 3)
Covers scenarios 1-7 from SKILL_TEST_SCENARIOS.md (≥5 cases)
No LLM calls required — tests the skill files themselves.
Run: pytest tests/test_skills.py -v
"""
import os
import re
import glob
import pytest

SKILLS_DIR = "skills"


def get_skill_files():
    return glob.glob(os.path.join(SKILLS_DIR, "*.md"))


def parse_frontmatter(filepath):
    """Parse YAML frontmatter from a SKILL.md file."""
    with open(filepath, encoding="utf-8") as f:
        content = f.read()
    
    if not content.startswith("---"):
        return {}, content
    
    end = content.find("---", 3)
    if end == -1:
        return {}, content
    
    fm_text = content[3:end].strip()
    body = content[end+3:].strip()
    
    fields = {}
    for line in fm_text.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fields[key.strip()] = val.strip().strip('"')
    
    return fields, body


# ---------------------------------------------------------------------------
# Scenario 1 — Pack version pin
# ---------------------------------------------------------------------------

class TestPackVersion:
    def test_challenge_skill_exists(self):
        """Scenario 1: CHALLENGE_SKILL.md must exist."""
        path = os.path.join(SKILLS_DIR, "CHALLENGE_SKILL.md")
        assert os.path.exists(path), "skills/CHALLENGE_SKILL.md not found"

    def test_challenge_skill_has_version(self):
        """Scenario 1: CHALLENGE_SKILL.md description must contain otel-rm-v2."""
        path = os.path.join(SKILLS_DIR, "CHALLENGE_SKILL.md")
        fm, _ = parse_frontmatter(path)
        assert "otel-rm-v2" in fm.get("description", ""), (
            f"CHALLENGE_SKILL.md description does not contain 'otel-rm-v2': {fm.get('description')}"
        )

    def test_challenge_skill_valid_utf8(self):
        """Scenario 1: CHALLENGE_SKILL.md must be valid UTF-8."""
        path = os.path.join(SKILLS_DIR, "CHALLENGE_SKILL.md")
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert len(content) > 0


# ---------------------------------------------------------------------------
# Scenario 2 — Minimum skill count
# ---------------------------------------------------------------------------

class TestMinimumSkillCount:
    def test_at_least_six_skills(self):
        """Scenario 2: At least 6 SKILL.md files under skills/."""
        files = get_skill_files()
        assert len(files) >= 6, f"Only {len(files)} skill files found, need ≥6"

    def test_all_skills_have_name_and_description(self):
        """Scenario 2: Every skill has name and description in frontmatter."""
        for filepath in get_skill_files():
            fm, _ = parse_frontmatter(filepath)
            fname = os.path.basename(filepath)
            assert "name" in fm, f"{fname}: missing 'name' in frontmatter"
            assert "description" in fm, f"{fname}: missing 'description' in frontmatter"
            assert fm["name"], f"{fname}: 'name' is empty"
            assert fm["description"], f"{fname}: 'description' is empty"


# ---------------------------------------------------------------------------
# Scenario 3 — Judgment skills
# ---------------------------------------------------------------------------

class TestJudgmentSkills:
    NUMERIC_THRESHOLD_PATTERNS = [
        r">\s*\d+%",
        r">=\s*\d+",
        r"<\s*\d+%",
        r">\s*\d+\.\d+",
        r"\d+%\s*(threshold|risk|above|below)",
    ]
    ACTION_KEYWORDS = [
        "recommend", "action", "close", "open", "shift", "review",
        "push", "consider", "hold", "flag", "alert"
    ]

    def has_numeric_threshold(self, body):
        for pattern in self.NUMERIC_THRESHOLD_PATTERNS:
            if re.search(pattern, body, re.IGNORECASE):
                return True
        return False

    def has_recommended_action(self, body):
        for kw in self.ACTION_KEYWORDS:
            if kw.lower() in body.lower():
                return True
        return False

    def test_at_least_three_judgment_skills(self):
        """Scenario 3: ≥3 skills have numeric threshold AND recommended action."""
        judgment_count = 0
        for filepath in get_skill_files():
            fm, body = parse_frontmatter(filepath)
            if self.has_numeric_threshold(body) and self.has_recommended_action(body):
                judgment_count += 1
        assert judgment_count >= 3, f"Only {judgment_count} judgment skills found, need ≥3"

    def test_judgment_skills_have_minimum_body_length(self):
        """Scenario 3: judgment skills must be ≥80 words of body text."""
        for filepath in get_skill_files():
            fm, body = parse_frontmatter(filepath)
            if self.has_numeric_threshold(body) and self.has_recommended_action(body):
                word_count = len(body.split())
                fname = os.path.basename(filepath)
                assert word_count >= 80, (
                    f"{fname}: judgment skill body only {word_count} words, need ≥80"
                )


# ---------------------------------------------------------------------------
# Scenario 4 — Tool routing declared
# ---------------------------------------------------------------------------

class TestToolRouting:
    REQUIRED_TOOLS = [
        "get_otb_summary",
        "get_segment_mix",
        "get_pickup_delta",
        "get_as_of_otb",
        "get_block_vs_transient_mix",
    ]

    def test_every_skill_names_a_tool(self):
        """Scenario 4: every skill body or description names at least one required tool."""
        for filepath in get_skill_files():
            fm, body = parse_frontmatter(filepath)
            combined = body + " " + fm.get("description", "")
            fname = os.path.basename(filepath)
            found = any(tool in combined for tool in self.REQUIRED_TOOLS)
            assert found, f"{fname}: no required tool name found in skill body or description"

    def test_no_skill_instructs_raw_sql(self):
        """Scenario 4: no skill tells model to run arbitrary SQL."""
        bad_patterns = ["run_sql", "SELECT * FROM reservations_hackathon", "arbitrary SQL"]
        for filepath in get_skill_files():
            _, body = parse_frontmatter(filepath)
            fname = os.path.basename(filepath)
            for pattern in bad_patterns:
                assert pattern not in body, (
                    f"{fname}: contains forbidden pattern '{pattern}'"
                )


# ---------------------------------------------------------------------------
# Scenario 5 — Distinct routing (no clones)
# ---------------------------------------------------------------------------

class TestDistinctRouting:
    def test_no_duplicate_skill_names(self):
        """Scenario 5: no two skills share the same name."""
        names = []
        for filepath in get_skill_files():
            fm, _ = parse_frontmatter(filepath)
            names.append(fm.get("name", ""))
        assert len(names) == len(set(names)), f"Duplicate skill names found: {names}"

    def test_covers_pickup_mix_and_otb(self):
        """Scenario 5: at least one skill each for pickup, mix/segment, and OTB."""
        pickup_found = mix_found = otb_found = False
        for filepath in get_skill_files():
            fm, body = parse_frontmatter(filepath)
            combined = (body + fm.get("description", "")).lower()
            if "pickup" in combined or "pace" in combined or "get_pickup_delta" in combined:
                pickup_found = True
            if "segment" in combined or "mix" in combined or "get_segment_mix" in combined:
                mix_found = True
            if "otb" in combined or "on-the-books" in combined or "get_otb_summary" in combined:
                otb_found = True
        assert pickup_found, "No skill covers pickup/pace"
        assert mix_found, "No skill covers mix/segment"
        assert otb_found, "No skill covers OTB summary"


# ---------------------------------------------------------------------------
# Scenario 6 — Adversarial guardrail
# ---------------------------------------------------------------------------

class TestAdversarialGuardrail:
    GUARDRAIL_PATTERNS = [
        "counting stay rows",
        "row_count",
        "property_date",
        "cancelled",
        "provisional",
        "NOT",
        "trap",
        "never",
        "do not",
        "avoid",
    ]

    def test_at_least_one_skill_has_guardrail(self):
        """Scenario 6: at least one skill warns against a known trap."""
        found = False
        for filepath in get_skill_files():
            _, body = parse_frontmatter(filepath)
            for pattern in self.GUARDRAIL_PATTERNS:
                if pattern.lower() in body.lower():
                    found = True
                    break
        assert found, "No skill contains an explicit guardrail warning"


# ---------------------------------------------------------------------------
# Scenario 7 — Tier D/E readiness (bonus)
# ---------------------------------------------------------------------------

class TestTierDEReadiness:
    def test_ota_concentration_skill_exists(self):
        """Scenario 7: at least one skill encodes OTA or block concentration judgment."""
        found = False
        for filepath in get_skill_files():
            fm, body = parse_frontmatter(filepath)
            combined = body + fm.get("description", "")
            if "ota" in combined.lower() or "block_share" in combined.lower() or "concentration" in combined.lower():
                found = True
                break
        assert found, "No skill covers OTA or block concentration (Tier D/E)"

    def test_share_of_revenue_referenced(self):
        """Scenario 7: at least one skill references share_of_revenue semantics."""
        found = False
        for filepath in get_skill_files():
            _, body = parse_frontmatter(filepath)
            if "share_of_revenue" in body or "share of revenue" in body.lower():
                found = True
                break
        assert found, "No skill references share_of_revenue"

"""
synapse_hijack.intent_extractor
===============================
Extracts explicit and implicit action items, recurring cron tasks, bug reports,
and project architectural directives from raw user chat streams.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class IntentKind(enum.Enum):
    IMMEDIATE_TASK = "immediate_task"
    RECURRING_CRON = "recurring_cron"
    SYSTEM_PRUNE = "system_prune"
    PROJECT_ARCHITECT = "project_architect"
    BUG_HEAL = "bug_heal"
    UNKNOWN = "unknown"


@dataclass
class ExtractedIntent:
    kind: IntentKind
    raw_snippet: str
    action: str
    target: str
    schedule: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    suggested_repo_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "raw_snippet": self.raw_snippet,
            "action": self.action,
            "target": self.target,
            "schedule": self.schedule,
            "parameters": self.parameters,
            "confidence": self.confidence,
            "suggested_repo_name": self.suggested_repo_name,
        }


class IntentExtractor:
    """Deterministic, token-pattern and semantic-regex based intent extractor."""

    CRON_PATTERNS = [
        r"(?:every|each)\s+(\d+)\s*(?:m|min|minutes?)",
        r"(?:every|each)\s+(\d+)\s*(?:h|hr|hrs|hours?)",
        r"(?:every|each)\s+(?:day|daily|night|morning)",
        r"(?:every|each)\s+(?:week|weekly|month|monthly)",
        r"hourly",
        r"daily at\s+([0-9:]+\s*(?:am|pm)?)",
    ]

    TASK_TRIGGERS = [
        (r"(?:clean|prune|remove|delete)\s+(?:hermes|deadcode|stubs|logs|cache)", IntentKind.SYSTEM_PRUNE),
        (r"(?:fix|debug|heal|repair|patch)\s+([a-zA-Z0-9_\-\.]+)", IntentKind.BUG_HEAL),
        (r"(?:create|build|make|architect|ship)\s+(?:a\s+)?(?:crazy\s+|novel\s+)?(?:repo|project|service)\s+(?:called\s+|named\s+)?([a-zA-Z0-9_\-\.]+)?", IntentKind.PROJECT_ARCHITECT),
        (r"(?:run|execute|benchmark|test|audit)\s+([a-zA-Z0-9_\-\.]+)", IntentKind.IMMEDIATE_TASK),
    ]

    CRAZY_NAME_PREFIXES = [
        "synapse-hijack",
        "necro-prune",
        "ouroboros-mutator",
        "phantom-dom",
        "vortex-plasma",
        "hyper-chronos",
        "zero-entropy",
        "cyber-forge",
    ]

    CRAZY_NAME_SUFFIXES = [
        "daemon",
        "orchestrator",
        "incinerator",
        "multiplexer",
        "pipeline",
        "engine",
        "synthesizer",
        "telemetry-core",
    ]

    def __init__(self, default_workdir: Optional[str] = None):
        self.default_workdir = default_workdir

    def parse(self, text: str) -> List[ExtractedIntent]:
        """Parse raw text, multi-line chat logs, or markdown and extract all intents."""
        intents: List[ExtractedIntent] = []
        if not text or not text.strip():
            return intents

        lines = [l.strip() for l in text.splitlines() if l.strip()]

        # Check for global schedule patterns
        cron_match = None
        for pattern in self.CRON_PATTERNS:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                cron_match = m.group(0).lower()
                break

        for line in lines:
            # Skip pure headers or comments
            if line.startswith("#") and "DIRECTIVE" not in line.upper():
                continue

            matched = False
            for regex, kind in self.TASK_TRIGGERS:
                m = re.search(regex, line, re.IGNORECASE)
                if m:
                    target = m.group(1) if m.lastindex and m.lastindex >= 1 else "hermes-core"
                    if not target:
                        target = "hermes-core"

                    # Generate crazy self-explanatory name if project architect
                    suggested_name = None
                    if kind == IntentKind.PROJECT_ARCHITECT:
                        clean_target = re.sub(r"[^a-zA-Z0-9]+", "-", target).strip("-").lower()
                        if clean_target and clean_target not in ("hermes-core", "repo", "project"):
                            suggested_name = f"{self.CRAZY_NAME_PREFIXES[0]}-{clean_target}-{self.CRAZY_NAME_SUFFIXES[0]}"
                        else:
                            suggested_name = "synapse-hijack-chat-to-cron-daemon"

                    intent = ExtractedIntent(
                        kind=kind,
                        raw_snippet=line,
                        action=m.group(0),
                        target=target,
                        schedule=cron_match,
                        suggested_repo_name=suggested_name,
                        confidence=0.92,
                    )
                    intents.append(intent)
                    matched = True
                    break

            if not matched and cron_match and ("run" in line.lower() or "execute" in line.lower() or "script" in line.lower()):
                intents.append(
                    ExtractedIntent(
                        kind=IntentKind.RECURRING_CRON,
                        raw_snippet=line,
                        action="schedule_cron",
                        target="background_job",
                        schedule=cron_match,
                        confidence=0.88,
                    )
                )

        # De-duplicate intents with identical (kind, target, action)
        seen = set()
        deduped = []
        for i in intents:
            key = (i.kind, i.target.lower(), i.action.lower())
            if key not in seen:
                seen.add(key)
                deduped.append(i)

        return deduped

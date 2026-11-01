"""
synapse-hijack-chat-to-cron-daemon
===================================
Autonomous omni-intent extraction, self-healing execution loops, and zero-touch chat-to-cron daemon for Hermes.
"""

from .intent_extractor import IntentExtractor, ExtractedIntent, IntentKind
from .self_healing_engine import SelfHealingEngine, ExecutionResult, StrategyKind
from .cron_bridge import CronBridge, CronJobDefinition
from .daemon import SynapseDaemon

__version__ = "0.1.0"
__all__ = [
    "IntentExtractor",
    "ExtractedIntent",
    "IntentKind",
    "SelfHealingEngine",
    "ExecutionResult",
    "StrategyKind",
    "CronBridge",
    "CronJobDefinition",
    "SynapseDaemon",
]

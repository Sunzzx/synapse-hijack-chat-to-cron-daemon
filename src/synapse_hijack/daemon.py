"""
synapse_hijack.daemon
=====================
Zero-touch background daemon:
- Watches chat inputs or history
- Ingests unhandled tasks
- Auto-executes self-healing loops
- Dispatches cron syncs
"""

from __future__ import annotations

import json
import os
import signal
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from .cron_bridge import CronBridge, CronJobDefinition
from .intent_extractor import IntentExtractor, IntentKind
from .self_healing_engine import SelfHealingEngine


class SynapseDaemon:
    """Autonomous chat-to-cron background listener."""

    def __init__(
        self,
        socket_path: Optional[str] = None,
        watch_file: Optional[Path] = None,
    ):
        self.socket_path = socket_path or "/tmp/synapse_hijack.sock"
        self.watch_file = watch_file or (Path.home() / ".hermes" / ".hermes_history")
        self.extractor = IntentExtractor()
        self.engine = SelfHealingEngine()
        self.bridge = CronBridge()
        self._running = False
        self._last_processed_mtime: float = 0.0

    def start_foreground(self):
        """Run the daemon in foreground."""
        self._running = True
        print(f"[SynapseDaemon] Starting foreground daemon on {self.socket_path}")

        # Clean socket if dangling
        if os.path.exists(self.socket_path):
            try:
                os.unlink(self.socket_path)
            except OSError:
                pass

        sock_thread = threading.Thread(target=self._socket_listener, daemon=True)
        sock_thread.start()

        print("[SynapseDaemon] Watching for autonomous chat events...")
        try:
            while self._running:
                self.tick_once()
                time.sleep(2.0)
        except KeyboardInterrupt:
            print("\n[SynapseDaemon] Shutting down.")
            self._running = False

    def tick_once(self) -> int:
        """Scan watched history file and process new lines."""
        if not self.watch_file.exists():
            return 0

        mtime = self.watch_file.stat().st_mtime
        if mtime <= self._last_processed_mtime:
            return 0

        self._last_processed_mtime = mtime
        try:
            with open(self.watch_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            
            # Look at recent lines
            recent = "".join(lines[-20:])
            intents = self.extractor.parse(recent)
            for intent in intents:
                self._dispatch_intent(intent)
            return len(intents)
        except Exception as e:
            print(f"[SynapseDaemon] Tick error: {e}", file=sys.stderr)
            return 0

    def _socket_listener(self):
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(self.socket_path)
        server.listen(5)
        server.settimeout(1.0)

        while self._running:
            try:
                conn, _ = server.accept()
                with conn:
                    data = conn.recv(16384).decode("utf-8")
                    if not data:
                        continue
                    intents = self.extractor.parse(data)
                    results = []
                    for intent in intents:
                        res = self._dispatch_intent(intent)
                        results.append({"intent": intent.to_dict(), "result": res})
                    conn.sendall(json.dumps(results).encode("utf-8"))
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    print(f"[SynapseDaemon] IPC socket error: {e}", file=sys.stderr)

    def _dispatch_intent(self, intent) -> str:
        if intent.kind == IntentKind.RECURRING_CRON:
            minutes = 60
            if "minute" in (intent.schedule or ""):
                minutes = 15
            elif "24" in (intent.schedule or "") or "daily" in (intent.schedule or ""):
                minutes = 1440
            
            job = CronJobDefinition(
                name=f"synapse-{intent.target}",
                prompt=f"Autonomous execution for {intent.target}",
                schedule_display=intent.schedule or "every 60m",
                minutes=minutes,
                no_agent=True,
            )
            self.bridge.upsert_job(job)
            return f"Scheduled cron job: {job.name}"

        elif intent.kind == IntentKind.IMMEDIATE_TASK:
            # Self-healing execute
            res = self.engine.execute_command(f"echo 'Executed immediate task: {intent.target}'")
            return res.summary()

        return f"Acknowledged intent: {intent.kind.value}"

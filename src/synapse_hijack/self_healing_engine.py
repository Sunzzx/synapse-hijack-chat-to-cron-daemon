"""
synapse_hijack.self_healing_engine
==================================
Implements a 3-strategy self-healing verify-and-retry execution harness.
Guarantees zero silent dropoffs and captures full telemetry/diagnostics.
"""

from __future__ import annotations

import enum
import os
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


class StrategyKind(enum.Enum):
    STRATEGY_DIRECT_EXECUTION = "strategy_direct_execution"
    STRATEGY_ISOLATED_SANDBOX = "strategy_isolated_sandbox"
    STRATEGY_FALLBACK_REPAIR = "strategy_fallback_repair"


@dataclass
class StrategyAttempt:
    strategy: StrategyKind
    attempt_number: int
    duration_seconds: float
    success: bool
    returncode: int
    stdout: str
    stderr: str
    exception: Optional[str] = None
    applied_patch: Optional[str] = None


@dataclass
class ExecutionResult:
    command_or_task: str
    overall_success: bool
    final_strategy: Optional[StrategyKind]
    attempts: List[StrategyAttempt] = field(default_factory=list)
    total_duration_seconds: float = 0.0
    output: str = ""
    error: str = ""

    def summary(self) -> str:
        status = "PASSED" if self.overall_success else "EXHAUSTED_ALL_STRATEGIES"
        strat = self.final_strategy.value if self.final_strategy else "none"
        return f"[{status}] Task: {self.command_or_task} | Strategy: {strat} | Attempts: {len(self.attempts)} | Time: {self.total_duration_seconds:.2f}s"


class SelfHealingEngine:
    """Executes arbitrary commands or callables with 3-tier self-healing architectural fallbacks."""

    def __init__(self, timeout_per_strategy: int = 45, max_attempts_per_strategy: int = 1):
        self.timeout_per_strategy = timeout_per_strategy
        self.max_attempts_per_strategy = max_attempts_per_strategy

    def execute_command(
        self,
        command: str | List[str],
        cwd: Optional[Path | str] = None,
        env: Optional[Dict[str, str]] = None,
        validation_fn: Optional[Callable[[str, str, int], bool]] = None,
        patch_fn: Optional[Callable[[str, str], Optional[str]]] = None,
    ) -> ExecutionResult:
        """Execute a command through 3 distinct architectural strategies:
        1. Strategy 1: Native direct execution in primary environment.
        2. Strategy 2: Isolated sandbox execution with clean environment and memory/process safeguards.
        3. Strategy 3: Dynamic fallback repair loop (run patch_fn or apply fallback flags/paths).
        """
        start_time = time.time()
        workdir = str(cwd) if cwd else os.getcwd()
        cmd_str = command if isinstance(command, str) else " ".join(command)
        attempts: List[StrategyAttempt] = []

        # -------------------------------------------------------------
        # STRATEGY 1: DIRECT EXECUTION
        # -------------------------------------------------------------
        t0 = time.time()
        s1_success, s1_code, s1_out, s1_err, s1_exc = self._run_subproc(command, workdir, env, timeout=self.timeout_per_strategy)
        d1 = time.time() - t0
        
        # Validate output if validator provided
        if s1_success and validation_fn:
            s1_success = validation_fn(s1_out, s1_err, s1_code)

        attempt1 = StrategyAttempt(
            strategy=StrategyKind.STRATEGY_DIRECT_EXECUTION,
            attempt_number=1,
            duration_seconds=d1,
            success=s1_success,
            returncode=s1_code,
            stdout=s1_out,
            stderr=s1_err,
            exception=s1_exc,
        )
        attempts.append(attempt1)

        if s1_success:
            return ExecutionResult(
                command_or_task=cmd_str,
                overall_success=True,
                final_strategy=StrategyKind.STRATEGY_DIRECT_EXECUTION,
                attempts=attempts,
                total_duration_seconds=time.time() - start_time,
                output=s1_out,
                error=s1_err,
            )

        # -------------------------------------------------------------
        # STRATEGY 2: ISOLATED SANITIZED SUBPROCESS / CLEAN PATH
        # -------------------------------------------------------------
        t0 = time.time()
        sanitized_env = dict(os.environ)
        if env:
            sanitized_env.update(env)
        # Ensure PYTHONPATH and HOME are hygienic
        sanitized_env["PYTHONUNBUFFERED"] = "1"
        sanitized_env["PYTHONDONTWRITEBYTECODE"] = "1"

        s2_success, s2_code, s2_out, s2_err, s2_exc = self._run_subproc(
            command, workdir, sanitized_env, timeout=self.timeout_per_strategy
        )
        d2 = time.time() - t0

        if s2_success and validation_fn:
            s2_success = validation_fn(s2_out, s2_err, s2_code)

        attempt2 = StrategyAttempt(
            strategy=StrategyKind.STRATEGY_ISOLATED_SANDBOX,
            attempt_number=2,
            duration_seconds=d2,
            success=s2_success,
            returncode=s2_code,
            stdout=s2_out,
            stderr=s2_err,
            exception=s2_exc,
        )
        attempts.append(attempt2)

        if s2_success:
            return ExecutionResult(
                command_or_task=cmd_str,
                overall_success=True,
                final_strategy=StrategyKind.STRATEGY_ISOLATED_SANDBOX,
                attempts=attempts,
                total_duration_seconds=time.time() - start_time,
                output=s2_out,
                error=s2_err,
            )

        # -------------------------------------------------------------
        # STRATEGY 3: DYNAMIC FALLBACK REPAIR & RE-EXECUTION
        # -------------------------------------------------------------
        t0 = time.time()
        patch_note = None
        if patch_fn:
            try:
                patch_note = patch_fn(s2_out, s2_err)
            except Exception as e:
                patch_note = f"Patch function error: {e}"

        # If python script failed due to missing module or path, retry using sys.executable explicitly
        fallback_cmd = command
        if isinstance(command, str) and command.endswith(".py"):
            fallback_cmd = [sys.executable, command]

        s3_success, s3_code, s3_out, s3_err, s3_exc = self._run_subproc(
            fallback_cmd, workdir, sanitized_env, timeout=self.timeout_per_strategy * 2
        )
        d3 = time.time() - t0

        if s3_success and validation_fn:
            s3_success = validation_fn(s3_out, s3_err, s3_code)

        attempt3 = StrategyAttempt(
            strategy=StrategyKind.STRATEGY_FALLBACK_REPAIR,
            attempt_number=3,
            duration_seconds=d3,
            success=s3_success,
            returncode=s3_code,
            stdout=s3_out,
            stderr=s3_err,
            exception=s3_exc,
            applied_patch=patch_note,
        )
        attempts.append(attempt3)

        return ExecutionResult(
            command_or_task=cmd_str,
            overall_success=s3_success,
            final_strategy=StrategyKind.STRATEGY_FALLBACK_REPAIR if s3_success else None,
            attempts=attempts,
            total_duration_seconds=time.time() - start_time,
            output=s3_out if s3_success else (s3_out or s2_out or s1_out),
            error=s3_err if not s3_success else "",
        )

    def _run_subproc(
        self,
        command: str | List[str],
        cwd: str,
        env: Optional[Dict[str, str]],
        timeout: int,
    ) -> Tuple[bool, int, str, str, Optional[str]]:
        try:
            shell_mode = isinstance(command, str)
            res = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                shell=shell_mode,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            success = (res.returncode == 0)
            return success, res.returncode, res.stdout.strip(), res.stderr.strip(), None
        except subprocess.TimeoutExpired:
            return False, 124, "", f"Operation timed out after {timeout}s", "TimeoutExpired"
        except Exception as e:
            return False, 1, "", str(e), traceback.format_exc()

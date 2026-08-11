"""
CleaningService: wraps `ran-clean` (ran-cleaning-service), unchanged.

Why a subprocess call and not an import: ran-cleaning-service's 11 stages
are `exec()`'d verbatim slices of the original monolithic script sharing one
namespace (see that service's own README for why), not composable Python
functions -- there is no `clean(df) -> df` to import. Wrapping its existing,
already-verified CLI entry point is the correct integration here, not a
workaround: it means this refactor doesn't touch a single line of
already-working cleaning logic.
"""

from __future__ import annotations

import selectors
import subprocess
import sys
from pathlib import Path
from typing import Any


def _run_with_logging(cmd: list[str], log_path: Path) -> tuple[int, str, str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    with open(log_path, "w", encoding="utf-8") as f:
        header = f"=== Executing: {' '.join(cmd)} ===\n"
        sys.stdout.write(header)
        sys.stdout.flush()
        f.write(header)
        f.flush()

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1
        )
        sel = selectors.DefaultSelector()
        if proc.stdout:
            sel.register(proc.stdout, selectors.EVENT_READ, data="stdout")
        if proc.stderr:
            sel.register(proc.stderr, selectors.EVENT_READ, data="stderr")

        while sel.get_map():
            events = sel.select(timeout=0.1)
            for key, _ in events:
                stream = key.fileobj
                line = stream.readline()
                if not line:
                    sel.unregister(stream)
                    continue
                if key.data == "stdout":
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    stdout_lines.append(line)
                else:
                    sys.stderr.write(line)
                    sys.stderr.flush()
                    stderr_lines.append(line)
                f.write(line)
                f.flush()

        returncode = proc.wait()

    return returncode, "".join(stdout_lines), "".join(stderr_lines)


class CleaningService:
    def __init__(self, command: str = "ran-clean"):
        self.command = command

    def run(self, output_dir: str) -> dict[str, Any]:
        """Run ran-clean. It reads from its default input path
        (/data/raw/Network_Drive_Test.pkl) set via RAN_CLEAN_INPUT_FILE
        or its built-in default."""
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        log_file = out_path / "ran_clean.log"

        returncode, stdout, stderr = _run_with_logging(
            [self.command, "--output-dir", output_dir],
            log_file,
        )
        success = returncode == 0
        return {
            "success": success,
            "returncode": returncode,
            "output_dir": str(out_path.resolve()),
            "log_file": str(log_file.resolve()),
            "stdout_tail": "\n".join(stdout.splitlines()[-30:]),
            "stderr_tail": "\n".join(stderr.splitlines()[-30:]) if not success else "",
        }

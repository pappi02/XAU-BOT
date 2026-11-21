"""Logging setup (Phase 8.1, audit H-11).

`setup_logger` attached only a `StreamHandler(sys.stdout)`. There was no
`FileHandler` anywhere in the project, which contradicted the README's claim
that "Logs are written to console and files" -- so after a crash or an overnight
run there was nothing to read. A bot you cannot review after the fact is a bot
whose behaviour you can only guess at.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

DEFAULT_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

FORMAT = "%(asctime)s - %(levelname)s - %(message)s"


def setup_logger(name="xau_bot", level="INFO", log_dir=None,
                 max_bytes=5 * 1024 * 1024, backup_count=10):
    """Console + rotating file logger.

    Idempotent: repeated calls return the same configured logger rather than
    stacking handlers, which is why every module can call it freely.
    """
    logger = logging.getLogger(name)
    # Phase 1.7: do not propagate to the root logger. Library modules that call
    # logging.basicConfig() install a root handler, and every record was then
    # emitted twice -- once here and once at root.
    logger.propagate = False

    if logger.handlers:
        # Already configured. Do NOT reset the level: six modules call this at
        # import time, and several import lazily inside functions, so resetting
        # here silently undid any level a caller had deliberately set. The
        # backtester hit exactly this -- it turned logging down for a run, and
        # the first lazy `import RiskManager` inside the run turned it back up.
        return logger

    logger.setLevel(getattr(logging, str(level).upper(), logging.INFO))

    formatter = logging.Formatter(FORMAT)

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    logger.addHandler(stream)

    log_dir = log_dir or DEFAULT_LOG_DIR
    try:
        os.makedirs(log_dir, exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, "%s.log" % name),
            maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except (OSError, ValueError) as exc:
        # Losing the file log must not take the bot down, but it must be said.
        # ValueError too: a malformed path raises that rather than OSError.
        logger.error("Could not open the log file in %s: %s. Console only.",
                     log_dir, exc)

    return logger


class DecisionLog:
    """One structured JSON record per loop iteration (Phase 8.1).

    This is the primary debugging surface. A prose log tells you what happened;
    this tells you *why* -- every input to the decision and every gate that
    passed or blocked, in a form you can load into pandas and aggregate.

    Without it, answering "why did it not trade yesterday?" means re-reading
    thousands of lines of prose and inferring. That question comes up
    constantly in Phase 9.
    """

    def __init__(self, path=None, log_dir=None):
        log_dir = log_dir or DEFAULT_LOG_DIR
        self.path = path or os.path.join(log_dir, "decisions.jsonl")
        self._logger = logging.getLogger("xau_bot")
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
        except (OSError, ValueError):
            pass

    def record(self, **fields):
        """Append one decision record. Never raises."""
        record = {"ts": datetime.now(timezone.utc).isoformat()}
        record.update(fields)
        try:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, default=str) + "\n")
        except (OSError, ValueError) as exc:
            self._logger.error("Could not write the decision log: %s", exc)
        return record

    def read_all(self):
        """Every record, oldest first. Convenience for analysis and tests."""
        if not os.path.exists(self.path):
            return []
        records = []
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except ValueError:
                    continue
        return records

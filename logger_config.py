import logging
import sys
import os
import io

def setup_logger(name="xau_bot", level="INFO", log_to_file=True):
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not logger.handlers:
        # Always log to stdout for console output with cp1252 encoding and error replacement to handle emojis
        ch = logging.StreamHandler(io.open(sys.stdout.fileno(), 'w', encoding='cp1252', errors='replace', closefd=False))
        ch.setLevel(getattr(logging, level.upper(), logging.INFO))
        fmt = "%(asctime)s - %(levelname)s - %(message)s"
        ch.setFormatter(logging.Formatter(fmt))
        logger.addHandler(ch)

        # Also log to file if enabled
        if log_to_file:
            try:
                log_file = os.path.join(os.path.dirname(__file__), 'bot_logs.log')
                fh = logging.FileHandler(log_file, encoding='utf-8')
                fh.setLevel(getattr(logging, level.upper(), logging.INFO))
                fh.setFormatter(logging.Formatter(fmt))
                logger.addHandler(fh)
            except Exception as e:
                print(f"Failed to set up file logging: {e}")

    logger.propagate = False  # Prevent duplicate logs by not propagating to root logger
    return logger

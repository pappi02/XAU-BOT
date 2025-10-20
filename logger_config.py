import logging
import sys

def setup_logger(name="xau_bot", level="INFO"):
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not logger.handlers:
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(getattr(logging, level.upper(), logging.INFO))
        fmt = "%(asctime)s - %(levelname)s - %(message)s"
        ch.setFormatter(logging.Formatter(fmt))
        logger.addHandler(ch)
    return logger

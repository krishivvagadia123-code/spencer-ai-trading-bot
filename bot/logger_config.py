import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler
LOG_FILE=Path(__file__).parent.parent/"bot.log"
def get_logger(name="kite-bot"):
    logger=logging.getLogger(name)
    if logger.handlers: return logger
    logger.setLevel(logging.DEBUG)
    fmt=logging.Formatter(fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",datefmt="%Y-%m-%d %H:%M:%S")
    fh=RotatingFileHandler(LOG_FILE,maxBytes=5*1024*1024,backupCount=3); fh.setLevel(logging.DEBUG); fh.setFormatter(fmt)
    ch=logging.StreamHandler(); ch.setLevel(logging.INFO); ch.setFormatter(fmt)
    logger.addHandler(fh); logger.addHandler(ch); return logger

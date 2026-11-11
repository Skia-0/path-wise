import sys
import os
from loguru import logger

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

logger.remove()

# Console logging
logger.add(
    sys.stdout,
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)

# File logging
logger.add(
    "logs/pathwise_backend.log",
    rotation="10 MB",
    retention="14 days",
    level="DEBUG",
    enqueue=True
)
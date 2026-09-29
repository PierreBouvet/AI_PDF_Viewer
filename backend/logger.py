"""
Centralized structured logger for AI PDF Viewer.
"""
import logging
import os
import sys
import codecs

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'replace')
if hasattr(sys.stderr, 'buffer'):
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'replace')


def setup_logger(name: str = "AIPDFViewer") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG if os.environ.get("DEBUG_AI") == "1" else logging.INFO)
        
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG if os.environ.get("DEBUG_AI") == "1" else logging.INFO)
        
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False
        
    return logger

logger = setup_logger()

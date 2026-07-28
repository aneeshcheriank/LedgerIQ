import logging

from src.orchestrator import run_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Starting the PDF to Markdown conversion pipeline...")
    run_pipeline()

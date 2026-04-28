import logging
from pathlib import Path
from datetime import datetime


class PipelineLogger:
    def __init__(self, log_dir="./logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)

    def get_logger(self, name):
        logger = logging.getLogger(name)
        if not logger.handlers:
            formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

            log_file = self.log_dir / f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)

            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)

            logger.addHandler(file_handler)
            logger.addHandler(console_handler)
            logger.setLevel(logging.INFO)

        return logger

import logging
import json
import sys
from types import TracebackType
from typing import Type


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()  # Default log handling
        log = {
            "level": record.levelname,
            "message": self.formatMessage(record),
        }
        if isinstance(record.args, dict):
            log.update(record.args)
        if record.exc_info:
            log["traceback"] = self.formatException(record.exc_info)
        return json.dumps(log)


def handle_exception(type_: Type[BaseException], value: BaseException, traceback: TracebackType) -> None:
    logging.error("Uncaught Exception", exc_info=(type_, value, traceback))


def setup_json_logger(log_level: int) -> None:
    sys.excepthook = handle_exception
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(log_level)


if __name__ == "__main__":
    setup_json_logger(logging.INFO)
    logging.info("test", {"a lot": "of", "extra": ["information"]})
    int("exception")

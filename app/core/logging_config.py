import json
import logging
import sys
from contextvars import ContextVar

# Thread-safe ContextVar to hold request_id
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get()
        }
        if record.exc_info:
            log_data["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(log_data)

def setup_logging():
    root_logger = logging.getLogger()
    # Clear existing handlers to prevent duplicate outputs
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(JSONFormatter())
    
    root_logger.addHandler(stdout_handler)
    root_logger.setLevel(logging.INFO)

import logging
import sys

from app.core.config import settings

_SENSITIVE_KEYS = (
    "GEMINI_API_KEY",
    "WHATSAPP_ACCESS_TOKEN",
    "TELEGRAM_BOT_TOKEN",
    "password",
    "JWT_SECRET_KEY",
    "authorization",
)


class RedactSensitiveFilter(logging.Filter):
    """Best-effort filter that redacts obviously sensitive substrings from log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        for key in _SENSITIVE_KEYS:
            if key.lower() in msg.lower():
                record.msg = "[REDACTED LOG LINE CONTAINING SENSITIVE KEY]"
                record.args = ()
                break
        return True


def configure_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    handler.addFilter(RedactSensitiveFilter())

    root.handlers = [handler]

    # Quiet noisy third-party loggers a bit
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.DEBUG else logging.WARNING
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

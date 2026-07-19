"""Structured JSON logging config.

Every log line is JSON via python-json-logger; there's no print anywhere in the
codebase. extra={...} fields on a log call surface as top-level JSON keys.
"""


def build_logging(debug: bool) -> dict:
    level = "DEBUG" if debug else "INFO"
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": "pythonjsonlogger.json.JsonFormatter",
                "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
                "rename_fields": {"asctime": "ts", "levelname": "level", "name": "logger"},
            }
        },
        "handlers": {
            "console": {"class": "logging.StreamHandler", "formatter": "json"},
        },
        "root": {"handlers": ["console"], "level": level},
        "loggers": {
            "rates.ingest": {"handlers": ["console"], "level": "INFO", "propagate": False},
            "rates.api": {"handlers": ["console"], "level": "INFO", "propagate": False},
            "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        },
    }

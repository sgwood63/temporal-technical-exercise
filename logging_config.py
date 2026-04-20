import json
import logging
import logging.config
import sys
from pathlib import Path

_DEFAULT_CONFIG = Path("logging.json")


def configure_logging(level: str = "INFO", config_file: str | None = None) -> None:
    """Configure logging from a JSON dictConfig file or fall back to basicConfig.

    If config_file is not supplied, logging.json in the working directory is used
    automatically when it exists. Pass config_file="" to force stdout-only basicConfig
    even when logging.json is present.

    The LOG_CONFIG env var is the conventional way to override in worker.py;
    --log-config is the CLI equivalent in run_workflow.py.
    """
    resolved: Path | None = None

    if config_file is None and _DEFAULT_CONFIG.is_file():
        resolved = _DEFAULT_CONFIG
    elif config_file:
        resolved = Path(config_file)
        if not resolved.is_file():
            raise FileNotFoundError(f"Logging config file not found: {config_file}")

    if resolved:
        Path("logs").mkdir(exist_ok=True)
        with resolved.open() as fh:
            logging.config.dictConfig(json.load(fh))
        return

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
        force=True,
    )

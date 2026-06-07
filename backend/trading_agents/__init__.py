import warnings

try:
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv(usecwd=True))
    load_dotenv(find_dotenv(".env.enterprise", usecwd=True), override=False)
except ImportError:
    pass
try:
    from backend.trading_agents.agents.runtime.logging_config import setup_unified_logging

    setup_unified_logging()
except Exception as exc:
    import sys

    sys.stderr.write(f"Warning: Failed to set up unified logging: {exc}\n")
try:
    import langchain_core  # noqa: F401  (availability probe — imported for its side effects)
except ImportError:
    pass
warnings.filterwarnings(
    "ignore",
    message=r"The default value of `allowed_objects`.*",
    category=PendingDeprecationWarning,
)

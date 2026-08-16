"""Import every built-in tool module so it registers itself.

Tools register on import (``registry.register(...)`` at module scope), so
nothing reaches the registry unless something imports them. This module is that
something: ``main.py``, ``worker.py`` and ``schema_contracts`` import it purely
for the side effect, which is why the names below look unused.

``tests/test_ai_engine/test_tool_bootstrap.py`` asserts the registry is
non-empty after importing this module, because an empty file here is silent —
the app starts, the API answers, and every tool has simply vanished.
"""

from .builtin import (
    backtest,  # noqa: F401
    chart,  # noqa: F401
    core_stock,  # noqa: F401
    fundamentals,  # noqa: F401
    macro,  # noqa: F401
    news,  # noqa: F401
    options,  # noqa: F401
    ownership,  # noqa: F401
    quant,  # noqa: F401
    sentiment,  # noqa: F401
    technical_indicators,  # noqa: F401
)

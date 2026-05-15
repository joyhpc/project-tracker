"""Console compatibility helpers."""

from __future__ import annotations

import os
import sys


_ASCII_TRANSLATION = str.maketrans({
    "\ufe0f": "",
    "✅": "[OK]",
    "❌": "[ERR]",
    "⚠": "[WARN]",
    "🔴": "[HIGH]",
    "🟡": "[MED]",
    "🟢": "[LOW]",
    "📋": "[PROJECT]",
    "📊": "[PROGRESS]",
    "⏱": "[TIME]",
    "📍": "[PHASE]",
    "🔒": "[LOCK]",
    "🚫": "[BLOCKED]",
    "💡": "[TIP]",
    "🎯": "[TARGET]",
    "👥": "[PEOPLE]",
    "🔄": "[RUN]",
    "⏳": "[WAIT]",
    "📦": "[BOX]",
    "🆕": "[NEW]",
    "📝": "[NOTE]",
    "➕": "+",
    "🟦": "[READY]",
    "⚡": "[ACTIVE]",
    "●": "*",
    "○": "o",
    "→": "->",
    "←": "<-",
    "↔": "<->",
    "—": "-",
    "─": "-",
    "█": "#",
    "░": ".",
})


class _SafeTextStream:
    """Translate display glyphs before writing to legacy consoles."""

    _pt_safe_stream = True

    def __init__(self, stream):
        self._stream = stream

    def write(self, text):
        return self._stream.write(str(text).translate(_ASCII_TRANSLATION))

    def writelines(self, lines):
        return self._stream.writelines(str(line).translate(_ASCII_TRANSLATION) for line in lines)

    def __getattr__(self, name):
        return getattr(self._stream, name)


def configure_stdio() -> None:
    """Make CLI output tolerant of non-UTF-8 Windows consoles.

    The project prints Chinese text and status symbols heavily. On Windows,
    the default console encoding can be GBK, which cannot encode emoji and
    crashes plain ``print`` calls. Keeping the current encoding but replacing
    unencodable glyphs preserves Chinese output and avoids command failures.

    Set ``PT_FORCE_UTF8=1`` when the terminal is known to handle UTF-8.
    """

    force_utf8 = os.environ.get("PT_FORCE_UTF8") == "1"
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if not reconfigure:
            continue
        kwargs = {"errors": "replace"}
        if force_utf8:
            kwargs["encoding"] = "utf-8"
        try:
            reconfigure(**kwargs)
        except (OSError, ValueError):
            # Some captured streams cannot be reconfigured. In that case we
            # leave them untouched; callers still get the normal Python errors.
            pass

        encoding = (getattr(stream, "encoding", "") or "").lower()
        if not force_utf8 and encoding and "utf" not in encoding and not getattr(stream, "_pt_safe_stream", False):
            setattr(sys, name, _SafeTextStream(stream))

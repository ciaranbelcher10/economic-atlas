"""Strip API keys from everything a pipeline script prints (v1.7.42).

Importing this module wraps sys.stdout and sys.stderr so any text
containing ``api_key=<value>`` is written as ``api_key=***``. That covers
printed exceptions (requests puts the full URL, key included, in
raise_for_status() messages) and uncaught tracebacks alike, so a local
log or an uploaded log can never carry the FRED key again.
"""
from __future__ import annotations

import re
import sys

_PAT = re.compile(r"(api_key=)[^&\s'\"]+")


def redact(text) -> str:
    return _PAT.sub(r"\1***", str(text))


class _Redacting:
    def __init__(self, inner):
        self._inner = inner

    def write(self, s):
        return self._inner.write(redact(s))

    def writelines(self, lines):
        for line in lines:
            self.write(line)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def install():
    if not isinstance(sys.stdout, _Redacting):
        sys.stdout = _Redacting(sys.stdout)
    if not isinstance(sys.stderr, _Redacting):
        sys.stderr = _Redacting(sys.stderr)


install()

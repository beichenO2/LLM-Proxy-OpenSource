"""Regex-based PII pattern scanner.

Detects common PII types in arbitrary text without requiring
pre-registered identity data. Returns match positions and type labels.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = []


def _register(label: str, desc: str, pattern: str, flags: int = 0) -> None:
    _PATTERNS.append((label, desc, re.compile(pattern, flags)))


_register("email", "邮箱地址", r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}(?![A-Za-z0-9])")
_register("phone_cn", "中国手机号", r"(?<!\d)1[3-9]\d{9}(?!\d)")
_register("phone_intl", "国际电话号码", r"\+\d{1,3}[\s\-]?\d{2,4}[\s\-]?\d{4,8}")
_register("id_card_cn", "中国身份证号", r"(?<!\d)\d{17}[\dXx](?!\d)")
_register("bank_card", "银行卡号(16-19位)", r"(?<!\d)(?:4\d{15}|5[1-5]\d{14}|6\d{15,18}|62\d{14,17})(?!\d)")
_register("ipv4", "IPv4 地址", r"(?<!\d)(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?!\d)")
_register("ipv6", "IPv6 地址", r"(?<![0-9a-fA-F:])(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}(?![0-9a-fA-F])")
_register("api_key", "API Key / Token", r"(?<![A-Za-z0-9_\-])(?:sk|pk|ak|rk|key|token|bearer|secret)[_\-][A-Za-z0-9\-_]{16,}(?![A-Za-z0-9_\-])", re.IGNORECASE)
_register("jwt", "JWT Token", r"(?<![A-Za-z0-9])eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+(?![A-Za-z0-9_\-])")
_register("passport_cn", "中国护照号", r"(?<![A-Za-z0-9])[EeGg]\d{8}(?!\d)")
_register("url_with_token", "含 token 的 URL", r"https?://[^\s]+[?&](?:token|key|secret|api_key|access_token)=[^\s&]+", re.IGNORECASE)


@dataclass
class PiiMatch:
    label: str
    description: str
    start: int
    end: int
    text: str


@dataclass
class ScanResult:
    matches: list[PiiMatch] = field(default_factory=list)

    @property
    def has_pii(self) -> bool:
        return len(self.matches) > 0


def scan_text(text: str) -> ScanResult:
    """Scan text for PII patterns and return all matches."""
    matches: list[PiiMatch] = []
    seen: set[tuple[int, int]] = set()

    for label, desc, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            span = (m.start(), m.end())
            if span in seen:
                continue
            seen.add(span)
            matches.append(PiiMatch(
                label=label,
                description=desc,
                start=m.start(),
                end=m.end(),
                text=m.group(),
            ))

    matches.sort(key=lambda x: x.start)
    return ScanResult(matches=matches)


def redact_text(text: str, placeholder: str = "[[{label}]]") -> tuple[str, ScanResult]:
    """Scan and replace all PII matches with placeholders.

    Returns (redacted_text, scan_result).
    """
    result = scan_text(text)
    if not result.has_pii:
        return text, result

    parts: list[str] = []
    last = 0
    for m in result.matches:
        parts.append(text[last:m.start])
        parts.append(placeholder.format(label=m.label, description=m.description, text=m.text))
        last = m.end
    parts.append(text[last:])
    return "".join(parts), result


def get_patterns() -> list[dict[str, str]]:
    """Return all registered patterns for frontend display."""
    return [{"label": label, "description": desc, "pattern": p.pattern} for label, desc, p in _PATTERNS]


_custom_patterns: list[tuple[str, str, re.Pattern[str]]] = []


def add_custom_pattern(label: str, description: str, pattern: str, flags: int = 0) -> None:
    """Register a user-defined PII detection pattern at runtime."""
    compiled = re.compile(pattern, flags)
    for i, (l, _, _) in enumerate(_custom_patterns):
        if l == label:
            _custom_patterns[i] = (label, description, compiled)
            for j, (pl, _, _) in enumerate(_PATTERNS):
                if pl == label:
                    _PATTERNS[j] = (label, description, compiled)
                    break
            return
    _custom_patterns.append((label, description, compiled))
    _PATTERNS.append((label, description, compiled))


def remove_custom_pattern(label: str) -> bool:
    """Remove a user-defined pattern by label. Returns True if found."""
    global _custom_patterns
    before = len(_custom_patterns)
    _custom_patterns = [(l, d, p) for l, d, p in _custom_patterns if l != label]
    for i, (l, _, _) in enumerate(_PATTERNS):
        if l == label:
            _PATTERNS.pop(i)
            break
    return len(_custom_patterns) < before


def get_custom_patterns() -> list[dict[str, str]]:
    """Return only user-defined custom patterns."""
    return [{"label": l, "description": d, "pattern": p.pattern} for l, d, p in _custom_patterns]


def load_custom_patterns_from_db(db_rows: list[tuple[str, str, str]]) -> int:
    """Bulk-load custom patterns from DB rows (label, description, pattern). Returns count loaded."""
    loaded = 0
    for label, description, pattern in db_rows:
        try:
            add_custom_pattern(label, description, pattern)
            loaded += 1
        except re.error:
            pass
    return loaded

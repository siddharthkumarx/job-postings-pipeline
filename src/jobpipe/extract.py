"""Structured hints from a job description, computed in memory only.

The description text is never returned, logged or stored. Only these leave:
salary range (min, max, currency, period), a remote/hybrid/onsite hint, a
seniority hint from "N+ years" phrases, the SHA-256 of the normalised text and
its length.
"""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def to_text(description: str | None) -> str:
    """HTML (possibly entity-escaped twice, as Greenhouse sends it) → plain text."""
    if not description:
        return ""
    text = html.unescape(html.unescape(description))
    text = _TAG.sub(" ", text)
    return _WS.sub(" ", text).strip()


@dataclass(frozen=True, slots=True)
class Salary:
    min: float
    max: float
    currency: str
    period: str


@dataclass(frozen=True, slots=True)
class DescriptionFacts:
    salary: Salary | None
    remote_hint: str | None
    seniority_hint: str | None
    sha256: str | None
    chars: int | None


_CUR_PREFIX = (
    r"(?P<cur>CA\$|C\$|A\$|AU\$|NZ\$|S\$|US\$|USD\s?|CAD\s?|AUD\s?|GBP\s?|EUR\s?|INR\s?|"
    r"\$|£|€|₹)"
)
_NUM = r"(?P<{n}>\d{{1,3}}(?:[,.\s]\d{{3}})+(?:[.,]\d{{1,2}})?|\d+(?:\.\d+)?)\s?(?P<{n}k>[kK])?"
_RANGE = re.compile(
    _CUR_PREFIX
    + r"\s?"
    + _NUM.format(n="a")
    + r"\s?(?:USD|CAD|AUD|GBP|EUR)?(?:\s?/\s?(?:hr|hour|yr|year))?"
    + r"\s?(?:-|–|—|to)\s?(?:CA\$|C\$|A\$|US\$|\$|£|€|₹)?\s?"
    + _NUM.format(n="b")
    + r"(?P<cur2>\s?(?:USD|CAD|AUD|GBP|EUR|INR))?",
)
_SINGLE = re.compile(
    _CUR_PREFIX
    + r"\s?"
    + _NUM.format(n="a")
    + r"(?P<cur2>\s?(?:USD|CAD|AUD|GBP|EUR))?"
    + r"\s?(?=(?:/|per |an |a )\s?(?:hour|hr|year|yr|annum|month|week))",
    re.IGNORECASE,
)
_PERIOD = [
    ("hour", re.compile(r"^\W{0,3}(?:/\s?h(?:ou)?r|per hour|an hour|hourly|/hour|p/h)", re.I)),
    ("year", re.compile(r"^\W{0,3}(?:/\s?y(?:ea)?r|per year|a year|annual|per annum|/yr)", re.I)),
    ("month", re.compile(r"^\W{0,3}(?:/\s?mo(?:nth)?|per month|a month|monthly)", re.I)),
    ("week", re.compile(r"^\W{0,3}(?:/\s?w(?:ee)?k|per week|a week|weekly)", re.I)),
    ("day", re.compile(r"^\W{0,3}(?:/\s?day|per day|a day|daily)", re.I)),
]
_CURRENCY_MAP = {
    "$": "USD", "US$": "USD", "USD": "USD", "CA$": "CAD", "C$": "CAD", "CAD": "CAD",
    "A$": "AUD", "AU$": "AUD", "AUD": "AUD", "NZ$": "NZD", "S$": "SGD", "£": "GBP",
    "GBP": "GBP", "€": "EUR", "EUR": "EUR", "₹": "INR", "INR": "INR",
}  # fmt: skip
_BOUNDS = {
    "year": (10_000, 2_000_000),
    "month": (1_000, 200_000),
    "week": (250, 40_000),
    "day": (50, 8_000),
    "hour": (7, 1_000),
}


def _num(raw: str, k: str | None) -> float:
    """Parse "120,000", "120.000", "120,000.00", "140.000,00", "140.000.00", "57.50"."""
    digits = raw.replace(" ", "")
    m = re.fullmatch(r"(\d{1,3}(?:[,.]\d{3})+)(?:[,.](\d{1,2}))?", digits)
    if m:
        whole = float(re.sub(r"[,.]", "", m.group(1)))
        value = whole + (float(f"0.{m.group(2)}") if m.group(2) else 0.0)
    else:
        try:
            value = float(digits.replace(",", ""))
        except ValueError:
            return float("nan")
    return value * 1000 if k else value


def _period_after(text: str, end: int, lo: float) -> str:
    tail = text[end : end + 40]
    for period, pat in _PERIOD:
        if pat.search(tail):
            return period
    return "hour" if lo < 1000 else "year"


def find_salary(text: str) -> Salary | None:
    for m in _RANGE.finditer(text):
        lo = _num(m.group("a"), m.group("ak"))
        hi = _num(m.group("b"), m.group("bk"))
        if m.group("ak") and not m.group("bk") and hi < 1000:
            hi *= 1000
        if m.group("bk") and not m.group("ak") and lo < 1000:
            lo *= 1000
        lo, hi = min(lo, hi), max(lo, hi)
        cur_raw = (m.group("cur2") or m.group("cur")).strip().upper()
        currency = _CURRENCY_MAP.get(cur_raw, _CURRENCY_MAP.get(m.group("cur").strip(), "USD"))
        period = _period_after(text, m.end(), lo)
        b_lo, b_hi = _BOUNDS[period]
        if b_lo <= lo <= b_hi and b_lo <= hi <= b_hi and hi <= lo * 4:
            return Salary(lo, hi, currency, period)
    for m in _SINGLE.finditer(text):
        value = _num(m.group("a"), m.group("ak"))
        cur_raw = (m.group("cur2") or m.group("cur")).strip().upper()
        currency = _CURRENCY_MAP.get(cur_raw, "USD")
        period = _period_after(text, m.end(), value)
        b_lo, b_hi = _BOUNDS[period]
        if b_lo <= value <= b_hi:
            return Salary(value, value, currency, period)
    return None


_HYBRID = re.compile(
    r"\bhybrid\b|\b(?:[1-4]|one|two|three|four) days? (?:a|per) week (?:in|at) (?:the|our) office"
    r"|\bdays? (?:a|per) week in(?:-| )office\b",
    re.I,
)
_REMOTE = re.compile(
    r"\bfully remote\b|\b100% remote\b|\bremote[- ]first\b|\bremote[- ]friendly\b"
    r"|\bwork from anywhere\b|\bthis (?:is a |role is )?remote (?:role|position)\b",
    re.I,
)
_ONSITE = re.compile(
    r"\bon[- ]site\b|\bin[- ]office\b|\b5 days (?:a|per) week (?:in|at) (?:the|our) office\b",
    re.I,
)


def remote_hint(text: str) -> str | None:
    if _HYBRID.search(text):
        return "hybrid"
    if _REMOTE.search(text):
        return "remote"
    if _ONSITE.search(text):
        return "onsite"
    return None


_YEARS = re.compile(
    r"(\d{1,2})\s?\+?\s?(?:-|–|to)?\s?(?:\d{1,2})?\+?\s?years?(?:'|’)?\s(?:of\s)?"
    r"(?:[a-z/\- ]{0,40}?)"
    r"(?:experience|exp\b)",
    re.I,
)


def seniority_hint(text: str) -> str | None:
    years = [int(m.group(1)) for m in _YEARS.finditer(text) if int(m.group(1)) <= 25]
    if not years:
        return None
    y = max(years)
    if y <= 1:
        return "junior"
    if y <= 4:
        return "mid"
    if y <= 7:
        return "senior"
    return "staff_principal"


def _safe_salary(text: str) -> Salary | None:
    try:
        return find_salary(text)
    except (ValueError, ArithmeticError):
        return None  # odd number formats must never fail a run


def analyse(description: str | None) -> DescriptionFacts:
    text = to_text(description)
    if not text:
        return DescriptionFacts(None, None, None, None, None)
    return DescriptionFacts(
        salary=_safe_salary(text),
        remote_hint=remote_hint(text),
        seniority_hint=seniority_hint(text),
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        chars=len(text),
    )

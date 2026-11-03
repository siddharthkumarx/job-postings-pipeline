"""Location → country classification (recon) and US state lookup.

The recon step only needs one answer per job: is it open in the US, somewhere
else, or unknown ("Remote", "Hybrid", blank)? The silver layer reuses the same
tables for country/state/city parsing.

Rules, in order, per location segment (segments are split on ``;``, ``|``,
`` / ``, `` or `` and newlines):

1. explicit US markers: "United States", "USA", "U.S.", a standalone "US",
   "US-Remote", "Remote (US)" …
2. ``City, ST`` where ST is a US state/territory postal code, or a US state name;
3. a well-known US metro name ("San Francisco", "NYC", "Bay Area" …);
4. a non-US country name/code or a well-known non-US city → that country;
5. otherwise unknown.

Structured hints (Lever ``country``, Ashby ``addressCountry``) win over text.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

US_STATES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
    "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
    "PR": "Puerto Rico",
}  # fmt: skip
US_STATE_NAMES = {v.lower(): k for k, v in US_STATES.items()}

US_CITIES: dict[str, str] = {
    "new york city": "NY", "new york": "NY", "nyc": "NY", "brooklyn": "NY", "manhattan": "NY",
    "san francisco": "CA", "sf bay area": "CA", "bay area": "CA", "silicon valley": "CA",
    "los angeles": "CA", "san jose": "CA", "san diego": "CA", "palo alto": "CA",
    "mountain view": "CA", "menlo park": "CA", "sunnyvale": "CA", "santa clara": "CA",
    "redwood city": "CA", "oakland": "CA", "irvine": "CA", "santa monica": "CA",
    "seattle": "WA", "bellevue": "WA", "redmond": "WA", "kirkland": "WA",
    "austin": "TX", "dallas": "TX", "houston": "TX", "san antonio": "TX", "plano": "TX",
    "boston": "MA", "cambridge, ma": "MA", "somerville": "MA",
    "chicago": "IL", "denver": "CO", "boulder": "CO", "atlanta": "GA", "miami": "FL",
    "tampa": "FL", "orlando": "FL", "phoenix": "AZ", "scottsdale": "AZ", "tempe": "AZ",
    "portland, or": "OR", "salt lake city": "UT", "lehi": "UT", "provo": "UT",
    "minneapolis": "MN", "detroit": "MI", "ann arbor": "MI", "pittsburgh": "PA",
    "philadelphia": "PA", "raleigh": "NC", "durham": "NC", "charlotte": "NC",
    "nashville": "TN", "columbus": "OH", "cincinnati": "OH", "cleveland": "OH",
    "st. louis": "MO", "kansas city": "MO", "indianapolis": "IN", "baltimore": "MD",
    "arlington, va": "VA", "reston": "VA", "mclean": "VA", "washington, d.c.": "DC",
    "washington dc": "DC", "washington d.c.": "DC", "las vegas": "NV", "honolulu": "HI",
    "jersey city": "NJ", "hoboken": "NJ", "princeton": "NJ", "stamford": "CT",
    "new haven": "CT", "madison, wi": "WI", "milwaukee": "WI", "omaha": "NE",
    "sacramento": "CA", "berkeley": "CA", "emeryville": "CA", "south san francisco": "CA",
    "el segundo": "CA", "pasadena": "CA", "culver city": "CA", "san mateo": "CA",
    "foster city": "CA", "burlingame": "CA", "san carlos": "CA", "cupertino": "CA",
    "huntsville": "AL", "birmingham, al": "AL", "boise": "ID", "albuquerque": "NM",
    "richmond, va": "VA", "herndon": "VA", "chantilly": "VA", "bethesda": "MD",
    "rockville": "MD", "columbia, md": "MD", "louisville": "KY", "new orleans": "LA",
    "oklahoma city": "OK", "tulsa": "OK", "des moines": "IA", "madison": "WI",
}  # fmt: skip

# Country name / alias (lowercase) -> ISO 3166-1 alpha-2.
COUNTRIES: dict[str, str] = {
    "united states": "US", "united states of america": "US", "usa": "US", "u.s.a.": "US",
    "u.s.": "US", "america": "US",
    "canada": "CA", "mexico": "MX", "méxico": "MX", "brazil": "BR", "brasil": "BR",
    "argentina": "AR", "chile": "CL", "colombia": "CO", "peru": "PE", "uruguay": "UY",
    "costa rica": "CR", "guatemala": "GT", "panama": "PA", "dominican republic": "DO",
    "ecuador": "EC", "venezuela": "VE", "bolivia": "BO", "paraguay": "PY", "jamaica": "JM",
    "united kingdom": "GB", "uk": "GB", "u.k.": "GB", "england": "GB", "scotland": "GB",
    "wales": "GB", "northern ireland": "GB", "great britain": "GB", "ireland": "IE",
    "germany": "DE", "deutschland": "DE", "france": "FR", "spain": "ES", "españa": "ES",
    "portugal": "PT", "italy": "IT", "italia": "IT", "netherlands": "NL",
    "the netherlands": "NL", "belgium": "BE", "luxembourg": "LU", "switzerland": "CH",
    "austria": "AT", "denmark": "DK", "sweden": "SE", "norway": "NO", "finland": "FI",
    "iceland": "IS", "poland": "PL", "czech republic": "CZ", "czechia": "CZ",
    "slovakia": "SK", "hungary": "HU", "romania": "RO", "bulgaria": "BG", "greece": "GR",
    "croatia": "HR", "serbia": "RS", "slovenia": "SI", "estonia": "EE", "latvia": "LV",
    "lithuania": "LT", "ukraine": "UA", "turkey": "TR", "türkiye": "TR", "cyprus": "CY",
    "malta": "MT", "bosnia and herzegovina": "BA", "north macedonia": "MK", "albania": "AL",
    "moldova": "MD", "belarus": "BY", "russia": "RU", "armenia": "AM", "azerbaijan": "AZ",
    "israel": "IL", "united arab emirates": "AE", "uae": "AE", "saudi arabia": "SA",
    "qatar": "QA", "egypt": "EG", "morocco": "MA", "nigeria": "NG", "kenya": "KE",
    "south africa": "ZA", "ghana": "GH", "rwanda": "RW", "ethiopia": "ET", "tunisia": "TN",
    "jordan": "JO", "lebanon": "LB", "bahrain": "BH", "kuwait": "KW", "oman": "OM",
    "pakistan": "PK", "india": "IN", "sri lanka": "LK", "bangladesh": "BD", "nepal": "NP",
    "china": "CN", "hong kong": "HK", "taiwan": "TW", "japan": "JP", "south korea": "KR",
    "korea": "KR", "singapore": "SG", "malaysia": "MY", "indonesia": "ID",
    "philippines": "PH", "thailand": "TH", "vietnam": "VN", "viet nam": "VN",
    "australia": "AU", "new zealand": "NZ", "kazakhstan": "KZ", "uzbekistan": "UZ",
    "georgia (country)": "GE",
}  # fmt: skip

NON_US_CITIES: dict[str, str] = {
    "london": "GB", "manchester": "GB", "edinburgh": "GB", "cambridge, uk": "GB",
    "bristol": "GB", "belfast": "GB", "glasgow": "GB", "leeds": "GB", "dublin": "IE",
    "cork": "IE", "toronto": "CA", "vancouver": "CA", "montreal": "CA", "montréal": "CA",
    "ottawa": "CA", "calgary": "CA", "waterloo": "CA", "edmonton": "CA", "kitchener": "CA",
    "berlin": "DE", "munich": "DE", "münchen": "DE", "hamburg": "DE", "frankfurt": "DE",
    "cologne": "DE", "paris": "FR", "lyon": "FR", "amsterdam": "NL", "rotterdam": "NL",
    "utrecht": "NL", "the hague": "NL", "eindhoven": "NL", "brussels": "BE", "zurich": "CH",
    "zürich": "CH", "geneva": "CH", "lausanne": "CH", "vienna": "AT", "copenhagen": "DK",
    "stockholm": "SE", "gothenburg": "SE", "oslo": "NO", "helsinki": "FI", "madrid": "ES",
    "barcelona": "ES", "valencia": "ES", "lisbon": "PT", "porto": "PT", "milan": "IT",
    "rome": "IT", "warsaw": "PL", "krakow": "PL", "kraków": "PL", "wroclaw": "PL",
    "wrocław": "PL", "gdansk": "PL", "prague": "CZ", "brno": "CZ", "budapest": "HU",
    "bucharest": "RO", "cluj-napoca": "RO", "sofia": "BG", "athens": "GR", "zagreb": "HR",
    "belgrade": "RS", "tallinn": "EE", "riga": "LV", "vilnius": "LT", "kyiv": "UA",
    "kiev": "UA", "lviv": "UA", "istanbul": "TR", "tel aviv": "IL", "tel aviv-yafo": "IL",
    "jerusalem": "IL", "haifa": "IL", "herzliya": "IL", "dubai": "AE", "abu dhabi": "AE",
    "riyadh": "SA", "cairo": "EG", "lagos": "NG", "nairobi": "KE", "cape town": "ZA",
    "johannesburg": "ZA", "bangalore": "IN", "bengaluru": "IN", "hyderabad": "IN",
    "pune": "IN", "mumbai": "IN", "new delhi": "IN", "delhi": "IN", "gurgaon": "IN",
    "gurugram": "IN", "noida": "IN", "chennai": "IN", "kolkata": "IN", "ahmedabad": "IN",
    "karachi": "PK", "lahore": "PK", "islamabad": "PK", "colombo": "LK", "dhaka": "BD",
    "beijing": "CN", "shanghai": "CN", "shenzhen": "CN", "hangzhou": "CN", "taipei": "TW",
    "tokyo": "JP", "osaka": "JP", "seoul": "KR", "manila": "PH", "makati": "PH",
    "cebu": "PH", "jakarta": "ID", "kuala lumpur": "MY", "bangkok": "TH",
    "ho chi minh city": "VN", "hanoi": "VN", "sydney": "AU", "melbourne": "AU",
    "brisbane": "AU", "perth": "AU", "auckland": "NZ", "wellington": "NZ",
    "mexico city": "MX", "ciudad de méxico": "MX", "guadalajara": "MX", "monterrey": "MX",
    "são paulo": "BR", "sao paulo": "BR", "rio de janeiro": "BR", "florianópolis": "BR",
    "buenos aires": "AR", "santiago": "CL", "bogotá": "CO", "bogota": "CO",
    "medellín": "CO", "medellin": "CO", "lima": "PE", "montevideo": "UY",
    "san josé, costa rica": "CR", "tbilisi": "GE", "yerevan": "AM", "almaty": "KZ",
}  # fmt: skip

# Region words: definitely not US-only, but no single country.
NON_US_REGIONS = ("emea", "apac", "latam", "europe", "asia", "africa", "middle east", "oceania")
NON_US_REGION_CODE = "XX"

_SPLIT = re.compile(r"\s*(?:;|\||\n| / | or |•)\s*", re.IGNORECASE)
_US_MARKER = re.compile(
    r"(?<![a-z])(?:united states|u\.s\.a\.?|usa|u\.s\.)(?![a-z])"
    r"|(?-i:(?<![A-Za-z])US(?![A-Za-z]))"
    r"|\bus[- ](?:remote|based|only|east|west|central)\b"
    r"|\b(?:remote|anywhere)[ ,\-–(]*(?:in the )?us\b",
    re.IGNORECASE,
)
_STATE_CODE = re.compile(r",\s*([A-Z]{2})\b(?![a-z])")
_WORD_BOUNDARY_CACHE: dict[str, re.Pattern[str]] = {}

_HINTS: dict[str, str] = {
    "us": "US", "usa": "US", "united states": "US", "united states of america": "US",
}  # fmt: skip


def _word(term: str) -> re.Pattern[str]:
    pat = _WORD_BOUNDARY_CACHE.get(term)
    if pat is None:
        pat = re.compile(r"(?<![\w])" + re.escape(term) + r"(?![\w])", re.IGNORECASE)
        _WORD_BOUNDARY_CACHE[term] = pat
    return pat


def normalize_country_hint(hint: str) -> str | None:
    h = hint.strip().lower()
    if not h:
        return None
    if h in _HINTS:
        return _HINTS[h]
    if len(h) == 2 and h.isalpha():
        return h.upper()
    return COUNTRIES.get(h)


def split_locations(text: str) -> list[str]:
    return [s for s in (p.strip(" ,-–") for p in _SPLIT.split(text or "")) if s]


def classify_segment(segment: str) -> str | None:
    """Return an ISO-2 country code, ``XX`` for a non-US region, or None (unknown)."""
    seg = segment.strip()
    if not seg:
        return None
    low = seg.lower()
    if _US_MARKER.search(seg):
        return "US"
    for m in _STATE_CODE.finditer(seg):
        if m.group(1) in US_STATES:
            # "Berlin, DE" / "Toronto, CA" / "Bangalore, IN": a known non-US city
            # before an ambiguous code means the code is a country, not a state.
            before = low[: m.start()]
            for city, code in NON_US_CITIES.items():
                if _word(city).search(before):
                    return code
            return "US"
    for name in US_STATE_NAMES:
        if _word(name).search(low):
            if name == "georgia" and "tbilisi" in low:
                return "GE"
            return "US"
    for city in US_CITIES:
        if _word(city).search(low):
            return "US"
    for name, code in COUNTRIES.items():
        if _word(name).search(low):
            return code
    for city, code in NON_US_CITIES.items():
        if _word(city).search(low):
            return code
    for region in NON_US_REGIONS:
        if _word(region).search(low):
            return NON_US_REGION_CODE
    return None


def job_countries(locations: Iterable[str], hints: Iterable[str] = ()) -> set[str]:
    """All countries a job is open in (empty set = unknown)."""
    out: set[str] = set()
    for hint in hints:
        code = normalize_country_hint(hint)
        if code:
            out.add(code)
    for text in locations:
        for seg in split_locations(text):
            code = classify_segment(seg)
            if code:
                out.add(code)
    return out

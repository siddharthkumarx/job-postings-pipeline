"""Cheap per-board signals used to pick US tech companies during recon.

``is_tech_title`` is deliberately broad (engineering, data, product, design,
security, IT). It is *only* a company-selection signal; the versioned role
taxonomy used by the warehouse lives in dbt/seeds/role_taxonomy.csv.
"""

from __future__ import annotations

import re

TECH_TITLE = re.compile(
    r"\b("
    r"engineer\w*|engineering|developer|programmer|software|swe|sde|sre|devops|devsecops|"
    r"full[- ]?stack|front[- ]?end|back[- ]?end|mobile|ios|android|web|"
    r"data|analytics|analyst|scientist|machine learning|ml|ai|llm|nlp|computer vision|"
    r"deep learning|research(er)?|"
    r"platform|infrastructure|cloud|kubernetes|systems?|network|site reliability|"
    r"security|cyber\w*|appsec|"
    r"product manager|product management|product owner|product designer|product design|"
    r"ux|ui|designer|technical|technology|architect|qa|quality assurance|test automation|"
    r"firmware|embedded|hardware|robotics|blockchain|crypto|solutions? engineer|"
    r"it support|it specialist|it administrator|database|dba|bi"
    r")\b",
    re.IGNORECASE,
)


def is_tech_title(title: str) -> bool:
    return bool(TECH_TITLE.search(title or ""))

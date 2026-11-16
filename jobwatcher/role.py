"""The title rule: decides whether a posting is in the watched role.

Role: financial analyst / FP&A.
"""
import re

# A title is in the role when it matches INCLUDE and does not match EXCLUDE.
INCLUDE = re.compile(
    r"\bfp\s*&\s*a\b"                                  # FP&A, FP & A
    r"|\bfinancial planning\b"                         # Financial Planning & Analysis
    r"|\bstrategic finance\b"                          # what many tech firms call FP&A
    r"|\bfinanc(e|ial)\b.*\banalyst\b"                 # Financial Analyst, Finance Analyst, Finance ... Analyst
    r"|\banalyst\b.*\bfinanc(e|ial)\b",                # Analyst, Finance / Senior Analyst - Corporate Finance
    re.IGNORECASE,
)
EXCLUDE = re.compile(
    r"\bfinancial crimes?\b|\bengineer(ing)?\b|\bdeveloper\b|\bcompliance\b|\brecruit",
    re.IGNORECASE,
)


def in_role(title: str) -> bool:
    title = title or ""
    return bool(INCLUDE.search(title)) and not EXCLUDE.search(title)

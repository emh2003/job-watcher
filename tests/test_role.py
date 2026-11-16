"""The title rule."""
import pytest

from jobwatcher.role import in_role


@pytest.mark.parametrize("title", [
    "Financial Analyst",
    "Senior Financial Analyst, FP&A",
    "Finance Analyst II",
    "FP&A Manager",
    "FP & A Associate",
    "Manager, Financial Planning & Analysis",
    "Strategic Finance Lead, Go-to-Market",
    "Finance & Strategy Analyst",
    "Senior Analyst, Corporate Finance",
    "financial analyst intern",
])
def test_in_role(title):
    assert in_role(title)


@pytest.mark.parametrize("title", [
    "Software Engineer",
    "Data Analyst",
    "Financial Crimes Analyst",
    "Software Engineer, Finance Systems Analyst Tools",
    "Compliance Analyst, Financial Regulation",
    "Finance Recruiter",
    "Accountant",
    "Head of Finance",
    "",
    None,
])
def test_not_in_role(title):
    assert not in_role(title)

"""Every page renders without an exception, for the latest month and for a filtered slice.
Login is not part of this test: pages are run directly with the filters the entry script would set."""
from pathlib import Path

import pytest
from dotenv import load_dotenv
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1]
load_dotenv(APP / ".env")

import kpis  # noqa: E402

PAGES = sorted((APP / "views").glob("*.py"))
SLICES = [kpis.Filters(202512), kpis.Filters(202401, regions=("South",), priorities=("P1",))]


@pytest.mark.parametrize("page", PAGES, ids=[p.stem for p in PAGES])
@pytest.mark.parametrize("filters", SLICES, ids=["latest", "first-month-south-p1"])
def test_page_renders(page, filters):
    at = AppTest.from_file(str(page), default_timeout=60)
    at.session_state["filters"] = filters
    at.run()
    assert not at.exception, at.exception
    assert at.title, "the page rendered nothing"

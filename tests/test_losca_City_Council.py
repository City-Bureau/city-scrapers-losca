from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import CITY_COUNCIL
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.losca_City_Council import LoscaCityCouncilSpider

test_response = file_response(
    join(dirname(__file__), "files", "losca_City_Council.json"),
    url="https://lacity.primegov.com/api/v2/PublicPortal/ListUpcomingMeetings?_=1726255032697",  # noqa
)
spider = LoscaCityCouncilSpider()

freezer = freeze_time("2024-09-30")
freezer.start()

parsed_items = [item for item in spider.parse(test_response)]

freezer.stop()


def test_count():
    assert len(parsed_items) == 13


def test_title():
    assert parsed_items[0]["title"] == "Personnel, Audits, and Hiring Committee"
    assert parsed_items[1]["title"] == "SAP - Personnel, Audits, and Hiring Committee"


def test_description():
    assert parsed_items[0]["description"] == ""


def test_start():
    assert parsed_items[0]["start"] == datetime(2024, 10, 1, 8, 30)
    assert parsed_items[1]["start"] == datetime(2024, 10, 1, 8, 30)
    assert parsed_items[2]["start"] == datetime(2024, 10, 1, 10, 0)


def test_end():
    assert parsed_items[0]["end"] is None


def test_time_notes():
    assert parsed_items[0]["time_notes"] == ""


def test_id():
    assert (
        parsed_items[0]["id"]
        == "losca_City_Council/202410010830/x/personnel_audits_and_hiring_committee"
    )


def test_status():
    assert parsed_items[0]["status"] == "tentative"


def test_location():
    assert parsed_items[0]["location"] == {
        "name": "Office of the City Clerk",
        "address": "200 N Spring St, Room 360, Los Angeles, CA 90012",
    }


def test_source():
    assert parsed_items[0]["source"] == "https://clerk.lacity.gov/calendar"


def test_links():
    assert parsed_items[0]["links"] == [
        {"title": "video", "href": "https://youtube.com/watch?v=ewD_li_BkgU"}
    ]
    assert parsed_items[1]["links"] == [
        {"title": "video", "href": "https://youtube.com/watch?v=EX00DchXvkA"}
    ]
    assert parsed_items[2]["links"] == []


def test_classification():
    assert parsed_items[0]["classification"] == CITY_COUNCIL


@pytest.mark.parametrize("item", parsed_items)
def test_all_day(item):
    assert item["all_day"] is False

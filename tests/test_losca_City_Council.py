from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import CANCELLED, CITY_COUNCIL, PASSED, TENTATIVE
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.losca_City_Council import LoscaCityCouncilSpider


@pytest.fixture(scope="module")
def spider():
    return LoscaCityCouncilSpider()


@pytest.fixture(scope="module")
def meetings_response():
    return file_response(join(dirname(__file__), "files", "losca_City_Council.json"))


@pytest.fixture(scope="module")
def parsed_items(spider, meetings_response):
    with freeze_time("2026-02-27"):
        items = list(spider.parse(meetings_response))
    return items


def test_count(parsed_items):
    assert len(parsed_items) == 3


def test_title(parsed_items):
    assert parsed_items[0]["title"] == "City Council Meeting"
    assert parsed_items[1]["title"] == "City Council Meeting"
    assert parsed_items[2]["title"] == "City Council Meeting"


def test_description(parsed_items):
    assert parsed_items[0]["description"] == ""


def test_start(parsed_items):
    assert parsed_items[0]["start"] == datetime(2025, 1, 1, 10, 0, 0)
    assert parsed_items[1]["start"] == datetime(2025, 4, 18, 10, 0, 0)
    assert parsed_items[2]["start"] == datetime(2026, 3, 4, 10, 0, 0)


def test_end(parsed_items):
    assert parsed_items[0]["end"] is None
    assert parsed_items[1]["end"] is None
    assert parsed_items[2]["end"] is None


def test_time_notes(parsed_items):
    assert parsed_items[0]["time_notes"] == ""


def test_id(parsed_items):
    assert (
        parsed_items[0]["id"]
        == "losca_City_Council/202501011000/x/city_council_meeting"
    )
    assert (
        parsed_items[1]["id"]
        == "losca_City_Council/202504181000/x/city_council_meeting"
    )
    assert (
        parsed_items[2]["id"]
        == "losca_City_Council/202603041000/x/city_council_meeting"
    )


def test_status(parsed_items):
    assert parsed_items[0]["status"] == CANCELLED
    assert parsed_items[1]["status"] == PASSED
    assert parsed_items[2]["status"] == TENTATIVE


def test_location(parsed_items):
    expected = {
        "name": "Office of the City Clerk",
        "address": "200 N Spring St, Room 360, Los Angeles, CA 90012",
    }
    assert parsed_items[0]["location"] == expected
    assert parsed_items[1]["location"] == expected
    assert parsed_items[2]["location"] == expected


def test_source(parsed_items):
    assert parsed_items[0]["source"] == "https://clerk.lacity.gov/calendar"


def test_links(parsed_items):
    assert parsed_items[0]["links"] == [
        {
            "title": "Notice of Cancellation",
            "href": "https://lacity.primegov.com/Portal/Meeting?meetingTemplateId=136037",  # noqa
        }
    ]
    assert parsed_items[1]["links"] == [
        {
            "title": "Recess Notice",
            "href": "https://lacity.primegov.com/Portal/Meeting?meetingTemplateId=140330",  # noqa
        }
    ]
    assert parsed_items[2]["links"] == [
        {
            "title": "Agenda",
            "href": "https://lacity.primegov.com/Portal/Meeting?meetingTemplateId=151891",  # noqa
        }
    ]


def test_classification(parsed_items):
    assert parsed_items[0]["classification"] == CITY_COUNCIL


def test_all_day(parsed_items):
    for item in parsed_items:
        assert item["all_day"] is False

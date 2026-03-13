from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import BOARD
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.losca_Board_of_ed import LoscaBoardOfEdSpider

test_response = file_response(
    join(dirname(__file__), "files", "losca_Board_of_ed.html"),
    url="https://boe.lausd.org/apps/events/2026/03/calendar/?id=0",
)
spider = LoscaBoardOfEdSpider()

freezer = freeze_time("2026-03-10")
freezer.start()

parsed_items = [item for item in spider.parse(test_response, year=2026, month=3)]

freezer.stop()


def test_count():
    assert len(parsed_items) == 10


def test_title():
    assert parsed_items[0]["title"] == (
        "Special Board Meeting, Including Closed Session Items - "
        "Recessed until 03/10/26"
    )
    assert parsed_items[1]["title"] == (
        "Special Board Meeting, Including Closed Session Items "
        "RECESSED from 03/02/26"
    )


def test_description():
    assert parsed_items[0]["description"] == ""


def test_start():
    assert parsed_items[0]["start"] == datetime(2026, 3, 2, 10, 0)


def test_end():
    assert parsed_items[0]["end"] == datetime(2026, 3, 2, 14, 0)


def test_minutes_parsing():
    # Test March 18 Special Education Committee: 3:30 PM – 5:30 PM
    march_18_event = [
        item for item in parsed_items if "Special Education" in item["title"]
    ]
    assert len(march_18_event) == 1
    assert march_18_event[0]["start"] == datetime(2026, 3, 18, 15, 30)
    assert march_18_event[0]["end"] == datetime(2026, 3, 18, 17, 30)


def test_time_notes():
    assert parsed_items[0]["time_notes"] == ""


def test_id():
    assert (
        parsed_items[0]["id"]
        == "losca_Board_of_ed/202603021000/x/special_board_meeting_including_closed_session_items_recessed_until_03_10_26"  # noqa
    )


def test_status():
    assert parsed_items[0]["status"] == "passed"


def test_location():
    assert parsed_items[0]["location"] == {
        "name": "LAUSD Headquarters",
        "address": "333 South Beaudry Avenue, Board Room, Los Angeles, CA 90017",
    }


def test_source():
    assert (
        parsed_items[0]["source"]
        == "https://boe.lausd.org/apps/events/2026/03/calendar/?id=0"
    )


def test_links():
    assert parsed_items[0]["links"] == [
        {
            "title": "Meeting Details",
            "href": "https://boe.lausd.org/apps/events/2026/3/2/36082672/?id=0",
        }
    ]
    assert parsed_items[1]["links"] == [
        {
            "title": "Meeting Details",
            "href": "https://boe.lausd.org/apps/events/2026/3/10/36293863/?id=0",
        }
    ]


def test_classification():
    assert parsed_items[0]["classification"] == BOARD


@pytest.mark.parametrize("item", parsed_items)
def test_all_day(item):
    assert item["all_day"] is False

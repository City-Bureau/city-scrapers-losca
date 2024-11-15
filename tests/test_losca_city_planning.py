from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import COMMISSION
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.losca_city_planning import LoscaCityPlanningSpider

test_response = file_response(
    join(dirname(__file__), "files", "losca_City_Planning.json"),
    url="https://planning.lacity.gov/dcpapi/meetings/api/all/commissions/2024",
)
spider = LoscaCityPlanningSpider()

freezer = freeze_time("2024-10-21")
freezer.start()

parsed_items = [item for item in spider.parse(test_response)]

freezer.stop()


def test_title():
    assert parsed_items[0]["title"] == "City Planning Commission"


def test_description():
    assert (
        parsed_items[0]["description"]
        == "CITY PLANNING COMMISSION\r\nREGULAR MEETING AGENDA"
    )


def test_start():
    assert parsed_items[0]["start"] == datetime(2024, 10, 24, 0, 0)


def test_end():
    assert parsed_items[0]["end"] is None


def test_time_notes():
    assert parsed_items[0]["time_notes"] == ""


def test_id():
    assert parsed_items[0]["id"] == "losca_city_planning/202410240000/x/city_planning_commission"


def test_status():
    assert parsed_items[0]["status"] == "tentative"


def test_location():
    assert parsed_items[0]["location"] == {
        "name": "",
        "address": "1101 West Ventura Boulevard, 1515 South Veteran Avenue, 1523 South Veteran Avenue, 1666 North Vermont Avenue, 1642 – 1666 North Vermont Avenue, 4646 – 4650 West Prospect Avenue, 4685 – 4697 West Hollywood Boulevard",
    }


def test_source():
    assert (
        parsed_items[0]["source"]
        == "https://planning.lacity.gov/dcpapi/meetings/api/all/commissions/2024"
    )


def test_links():
    assert parsed_items[0]["links"] == []


def test_classification():
    assert parsed_items[0]["classification"] == COMMISSION


@pytest.mark.parametrize("item", parsed_items)
def test_all_day(item):
    assert item["all_day"] is False

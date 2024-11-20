import json
from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import BOARD
from freezegun import freeze_time

from city_scrapers.spiders.losca_metro_transit import LoscaMetroTransitSpider

freezer = freeze_time("2024-10-31")
freezer.start()

with open(join(dirname(__file__), "files", "losca_metro_transit.json"), "r", encoding="utf-8") as f:
    test_response = json.load(f)

spider = LoscaMetroTransitSpider()
parsed_items = [item for item in spider.parse_legistar(test_response)]

freezer.stop()


def test_title():
    assert parsed_items[0]["title"] == "Board of Directors - Regular Board Meeting"


def test_description():
    assert parsed_items[0]["description"] == ""


def test_start():
    assert parsed_items[0]["start"] == datetime(2024, 10, 31, 10, 0)


def test_end():
    assert parsed_items[0]["end"] is None


def test_time_notes():
    assert parsed_items[0]["time_notes"] == ""


def test_id():
    assert parsed_items[0]["id"] is None


def test_status():
    assert parsed_items[0]["status"] is None


def test_location():
    assert parsed_items[0]["location"] == {
        "name": "Board of Directors - Regular Board Meeting",
        'address': 'One Gateway Plaza, Los Angeles, CA 90012, \r\n'
        '3rd Floor, Metro Board Room Watch online:  '
        'https://boardagendas.metro.net \r\n'
        'Listen by phone: Dial 202-735-3323 and enter Access Code:\r\n'
        '5647249# (English) or 7292892# (Español) \r\n'
        '\r\n'
        'To give written or live public comment, please see the top of page 4',
        'name': 'Board of Directors - Regular Board Meeting',
    }


def test_source():
    assert parsed_items[0]["source"] == "https://metro.legistar.com/DepartmentDetail.aspx?ID=28529&GUID=44319A1A-B2B7-48CC-B857-ADCE9064573B"


def test_links():
    assert parsed_items[0]["links"] == [{
        "href": "https://metro.legistar.com/DepartmentDetail.aspx?ID=28529&GUID=44319A1A-B2B7-48CC-B857-ADCE9064573B",
        "title": "Board of Directors - Regular Board Meeting"
    },
        {
        "href": "https://metro.legistar.com/View.ashx?M=IC&ID=1196314&GUID=2D75E646-096C-4C3A-A6B9-4A938061D9A9",
        "title": "iCalendar"
    }]


def test_classification():
    assert parsed_items[0]["classification"] == BOARD


@pytest.mark.parametrize("item", parsed_items)
def test_all_day(item):
    assert item["all_day"] is False

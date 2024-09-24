from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import BOARD
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.losca_Board_of_ed import LoscaBoardOfEdSpider

test_response = file_response(
    join(dirname(__file__), "files", "losca_Board_of_ed.html"),
    url="https://www.lausd.org/site/RSS.aspx?DomainID=1057&ModuleInstanceID=73805&PageID=18628&PMIID=0",  # noqa
)
spider = LoscaBoardOfEdSpider()

freezer = freeze_time("2024-09-19")
freezer.start()

parsed_items = [item for item in spider.parse(test_response)]

freezer.stop()


def test_count():
    assert len(parsed_items) == 12


def test_title():
    assert parsed_items[0]["title"] == "Greening Schools & Climate Resilience Committee"
    assert parsed_items[1]["title"] == "Curriculum and Instruction Committee"


def test_description():
    assert parsed_items[0]["description"] == ""


def test_start():
    assert parsed_items[0]["start"] == datetime(2024, 9, 24, 13, 0)


def test_end():
    assert parsed_items[0]["end"] == datetime(2024, 9, 24, 16, 0)


def test_time_notes():
    assert parsed_items[0]["time_notes"] == ""


def test_id():
    assert (
        parsed_items[0]["id"]
        == "losca_Board_of_ed/202409241300/x/greening_schools_climate_resilience_committee"  # noqa
    )


def test_status():
    assert parsed_items[0]["status"] == "tentative"


def test_location():
    assert parsed_items[0]["location"] == {
        "name": "LAUSD Headquarters",
        "address": "333 South Beaudry Avenue, Board Room, Los Angeles, CA 90017",
    }


def test_source():
    assert (
        parsed_items[0]["source"]
        == "https://www.lausd.org/site/RSS.aspx?DomainID=1057&ModuleInstanceID=73805&PageID=18628&PMIID=0"  # noqa
    )


def test_links():
    assert parsed_items[0]["links"] == [
        {
            "title": "Meeting Details",
            "href": "https://www.lausd.org/site/Default.aspx?PageID=18628&amp;PageType=17&amp;DomainID=1057&amp;ModuleInstanceID=73805&amp;EventDateID=73502",  # noqa
        }
    ]
    assert parsed_items[1]["links"] == [
        {
            "title": "Meeting Details",
            "href": "https://www.lausd.org/site/Default.aspx?PageID=18628&amp;PageType=17&amp;DomainID=1057&amp;ModuleInstanceID=73805&amp;EventDateID=71879",  # noqa
        }
    ]


def test_classification():
    assert parsed_items[0]["classification"] == BOARD


@pytest.mark.parametrize("item", parsed_items)
def test_all_day(item):
    assert item["all_day"] is False

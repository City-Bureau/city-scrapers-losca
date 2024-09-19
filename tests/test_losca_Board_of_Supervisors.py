from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import BOARD
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.losca_Board_of_Supervisors import (
    LoscaBoardOfSupervisorsSpider,
)

test_response = file_response(
    join(dirname(__file__), "files", "losca_Board_of_Supervisors.html"),
    url="https://bos.lacounty.gov/board-meeting-agendas/",
)
spider = LoscaBoardOfSupervisorsSpider()

freezer = freeze_time("2024-09-17")
freezer.start()

parsed_items = [item for item in spider.parse(test_response)]

freezer.stop()


def test_count():
    assert len(parsed_items) == 10


@pytest.mark.parametrize(
    "index, expected_title",
    [
        (0, "Policy Presentations and Public Hearing Meeting"),
        (1, "Regular Board Meeting"),
        (2, "Public Hearing Meeting"),
        (3, "Regular Board Meeting"),
        (4, "Policy Presentations Meeting"),
        (5, "Regular Board Meeting"),
        (6, "Regular Board Meeting"),
        (7, "Regular Board Meeting"),
        (8, "Budget Deliberations Board Meeting"),
        (9, "Policy Presentations Meeting"),
    ],
)
def test_title(index, expected_title):
    assert parsed_items[index]["title"] == expected_title


def test_description():
    assert parsed_items[0]["description"] == ""


@pytest.mark.parametrize(
    "index, expected_start",
    [
        (0, datetime(2024, 9, 17, 9, 30)),
        (1, datetime(2024, 9, 10, 9, 30)),
        (2, datetime(2024, 8, 13, 11, 0)),  # Only meeting not at 9:30 AM
        (3, datetime(2024, 8, 6, 9, 30)),
        (4, datetime(2024, 7, 30, 9, 30)),
        (5, datetime(2024, 7, 23, 9, 30)),
        (6, datetime(2024, 7, 9, 9, 30)),
        (7, datetime(2024, 6, 25, 9, 30)),
        (8, datetime(2024, 6, 24, 9, 30)),
        (9, datetime(2024, 6, 18, 9, 30)),
    ],
)
def test_start(index, expected_start):
    assert parsed_items[index]["start"] == expected_start


def test_end():
    assert parsed_items[0]["end"] is None


def test_time_notes():
    assert parsed_items[0]["time_notes"] == ""


def test_id():
    assert (
        parsed_items[0]["id"]
        == "losca_Board_of_Supervisors/202409170930/x/policy_presentations_and_public_hearing_meeting"  # noqa
    )


@pytest.mark.parametrize(
    "index, expected_status",
    [
        (0, "tentative"),
        (1, "passed"),
        (2, "passed"),
        (3, "passed"),
        (4, "passed"),
        (5, "passed"),
        (6, "passed"),
        (7, "passed"),
        (8, "passed"),
        (9, "passed"),
    ],
)
def test_status(index, expected_status):
    assert parsed_items[index]["status"] == expected_status


def test_location():
    assert parsed_items[0]["location"] == {
        "name": "Kenneth Hahn Hall of Administration",
        "address": "500 West Temple Street, Room 381B, Los Angeles",
    }


def test_source():
    assert (
        parsed_items[0]["source"] == "https://bos.lacounty.gov/board-meeting-agendas/"
    )


def test_links():
    assert parsed_items[0]["links"] == [
        {
            "title": "Agenda",
            "href": "https://assets-us-01.kc-usercontent.com/0234f496-d2b7-00b6-17a4-b43e949b70a2/522b6a97-181f-4a4d-a472-798ee3c7fc75/091724%20Agenda.htm",  # noqa
        },
        {
            "title": "PDF",
            "href": "https://assets-us-01.kc-usercontent.com:443/0234f496-d2b7-00b6-17a4-b43e949b70a2/d2b9d6cf-737c-4128-a54f-f1384fb4992e/Agenda_091724_links.pdf",  # noqa
        },
    ]
    assert parsed_items[1]["links"] == [
        {
            "title": "Agenda",
            "href": "https://assets-us-01.kc-usercontent.com/0234f496-d2b7-00b6-17a4-b43e949b70a2/2493f102-41f1-4483-9b65-39329b13e7a8/091024%20Agenda.htm",  # noqa
        },
        {
            "title": "PDF",
            "href": "https://assets-us-01.kc-usercontent.com:443/0234f496-d2b7-00b6-17a4-b43e949b70a2/d2af8220-c0e3-4d89-8370-c376023e1caf/Agenda_091024_links.pdf",  # noqa
        },
        {
            "title": "Supplemental",
            "href": "https://assets-us-01.kc-usercontent.com/0234f496-d2b7-00b6-17a4-b43e949b70a2/d1f3938c-28ca-462b-a688-c5f35b74a5bb/091024%20Supplemental%20Agenda.htm",  # noqa
        },
        {
            "title": "PDF",
            "href": "https://assets-us-01.kc-usercontent.com:443/0234f496-d2b7-00b6-17a4-b43e949b70a2/d8e39c4e-4f9d-4582-b357-572366d4619b/091024.pdf",  # noqa
        },
    ]


def test_classification():
    assert parsed_items[0]["classification"] == BOARD


@pytest.mark.parametrize("item", parsed_items)
def test_all_day(item):
    assert item["all_day"] is False

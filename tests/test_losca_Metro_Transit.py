import json
import logging
from datetime import datetime
from os.path import dirname, join
from unittest.mock import MagicMock

import pytest
from city_scrapers_core.constants import (
    ADVISORY_COMMITTEE,
    BOARD,
    CANCELLED,
    COMMITTEE,
    FORUM,
    NOT_CLASSIFIED,
    PASSED,
    TENTATIVE,
)
from freezegun import freeze_time
from scrapy import Request, signals
from scrapy.http import HtmlResponse
from twisted.python.failure import Failure

from city_scrapers.spiders.losca_Metro_Transit import (
    LoscaMetroTransitSourceError,
    LoscaMetroTransitSpider,
)

CALENDAR_URL = "https://metro.legistar.com/Calendar.aspx"
HQ = "One Gateway Plaza, Los Angeles, CA 90012"
CALL_IN = (
    "Watch online:  https://boardagendas.metro.net \r\nListen by phone: Dial "
    "888-978-8818 and enter Access Code:\r\n5647249# (English) or 7292892# "
    "(Español)\r\n\r\nTo give written or live public comment, please see the "
    "top of page 4"
)


def event(name, date="3/4/2026", time="10:00 AM", location="", meeting_id=1, **kw):
    """One Legistar calendar row as the spider's _parse_legistar_events
    returns it, with the same keys as the live calendar."""
    base = f"https://metro.legistar.com/View.ashx?ID={meeting_id}&GUID=X"
    row = {
        "Name": {"label": name, "url": "https://metro.legistar.com/Dept.aspx"},
        "Meeting Date": date,
        "iCalendar": {"url": f"{base}&M=IC"},
        "Meeting Time": time,
        "Meeting Location": location,
        "Meeting Details": {
            "label": "Meeting\xa0details",
            "url": f"https://metro.legistar.com/MeetingDetail.aspx?ID={meeting_id}",
        },
        "Agenda": "Not\xa0available",
        "Accessible Agenda": "Not\xa0available",
        "Agenda Packet": "Not\xa0available",
        "Recap/Minutes": "Not\xa0available",
        "Accessible Minutes": "Not\xa0available",
        "Audio": "Not\xa0available",
        "eComment": "Not\xa0available",
    }
    row.update(kw)
    return row


def location_of(raw):
    return LoscaMetroTransitSpider()._parse_location({"Meeting Location": raw})


@pytest.fixture(scope="module")
def parsed_items():
    with open(
        join(dirname(__file__), "files", "losca_Metro_Transit.json"),
        "r",
        encoding="utf-8",
    ) as f:
        events = json.load(f)
    spider = LoscaMetroTransitSpider()
    with freeze_time("2026-03-05"):
        return list(spider.parse_legistar(events))


@pytest.fixture(scope="module")
def item(parsed_items):
    """Measure M Independent Taxpayer Oversight Committee, 3/4/2026."""
    return parsed_items[37]


def test_count(parsed_items):
    """96 rows: 65 meetings, 23 "(SAP)" Spanish rows and 8 test meetings."""
    assert len(parsed_items) == 65


def test_title(item):
    assert item["title"] == "Measure M Independent Taxpayer Oversight Committee"


def test_description(item):
    assert item["description"] == (
        "Watch online: https://boardagendas.metro.net Listen by phone: Dial "
        "888-978-8818 and enter Access Code: 5647249# (English) or 7292892# "
        "(Español) To give written or live public comment, please see the top "
        "of page 4"
    )


def test_start(item):
    assert item["start"] == datetime(2026, 3, 4, 10, 0)


def test_end(item):
    assert item["end"] is None


def test_time_notes(item):
    assert item["time_notes"] == ""


def test_id(item):
    assert (
        item["id"]
        == "losca_Metro_Transit/202603041000/x/measure_m_independent_taxpayer_oversight_committee"  # noqa
    )


def test_status(parsed_items, item):
    assert item["status"] == PASSED
    assert parsed_items[0]["status"] == CANCELLED
    assert parsed_items[6]["status"] == TENTATIVE


def test_location(item):
    assert item["location"] == {"name": "3rd Floor, Metro Board Room", "address": HQ}


def test_source(item):
    assert (
        item["source"]
        == "https://metro.legistar.com/MeetingDetail.aspx?ID=1371499&GUID=76F1ECE2-63B6-42CB-BAF2-835C73669277&Options=info|&Search="  # noqa
    )


def test_links(item):
    assert item["links"] == [
        {
            "href": "https://metro.legistar.com/View.ashx?M=A&ID=1371499&GUID=76F1ECE2-63B6-42CB-BAF2-835C73669277",  # noqa
            "title": "Agenda",
        },
        {
            "href": "https://metro.legistar.com/MeetingDetail.aspx?ID=1371499&GUID=76F1ECE2-63B6-42CB-BAF2-835C73669277&Options=info|&Search=",  # noqa
            "title": "Meeting Details",
        },
        {
            "href": "https://metro.legistar.com/Video.aspx?Mode=Granicus&ID1=3960&Mode2=Video",  # noqa
            "title": "Audio",
        },
        {
            "href": "https://metro.legistar.com/Video.aspx?Mode=Granicus&ID1=3961&Mode2=Video",  # noqa
            "title": "Spanish Audio",
        },
    ]


def test_spanish_audio_count(parsed_items):
    """All 16 "(SAP)" rows with audio in the fixture land on their meeting."""
    spanish = [
        link
        for item in parsed_items
        for link in item["links"]
        if link["title"] == "Spanish Audio"
    ]
    assert len(spanish) == 16


def test_no_sap_or_test_meetings(parsed_items):
    titles = {item["title"] for item in parsed_items}
    assert not [t for t in titles if "(SAP)" in t or "Test" in t]


def test_agenda_packet(parsed_items):
    assert parsed_items[60]["links"][1] == {
        "href": "https://metro.legistar.com/View.ashx?M=PA&ID=1361974&GUID=DE542D9A-E8DC-4678-A1A7-9710470CFAFA",  # noqa
        "title": "Agenda Packet",
    }


def test_cancelled_meeting_gets_usual_time(parsed_items):
    """The source shows "Canceled" instead of a time, so the meeting keeps the
    board's usual 10:00 AM start, which keeps its id unchanged downstream."""
    item = parsed_items[0]
    assert item["start"] == datetime(2026, 6, 25, 10, 0)
    assert item["status"] == CANCELLED
    assert item["time_notes"] == ""


def test_cancelled_meeting_without_usual_time(caplog):
    """A cancelled meeting whose title has no usual time keeps midnight, a
    warning and a time note."""
    spider = LoscaMetroTransitSpider()
    location = HQ + ", \r\n3rd Floor, Metro Board Room"
    row = event("Gateway Cities Service Council", time="Canceled", location=location)
    with caplog.at_level(logging.WARNING), freeze_time("2026-03-05"):
        meeting = spider._parse_meeting(row, "Gateway Cities Service Council", {})
    assert meeting["start"] == datetime(2026, 3, 4, 0, 0)
    assert meeting["status"] == CANCELLED
    assert meeting["time_notes"] == (
        "Please check the meeting attachment for start time details."
    )
    assert "No start time for 'Gateway Cities Service Council'" in caplog.text


def test_hybrid_location(parsed_items):
    assert parsed_items[61]["location"] == {
        "name": (
            "Metro El Monte Division 9 Building, "
            "Third Floor Service Council Conference Room"
        ),
        "address": "3449 Santa Anita Av, El Monte, CA 91731",
    }
    assert parsed_items[61]["description"] == "Hybrid In-Person/Virtual Meeting"


def test_three_line_location(parsed_items):
    assert parsed_items[35]["location"] == {
        "name": "Metro Talent Hub",
        "address": "8501 S. Evermont Pl., Los Angeles, CA 90044",
    }


def test_classification(parsed_items):
    assert parsed_items[0]["classification"] == BOARD
    assert parsed_items[2]["classification"] == COMMITTEE
    assert parsed_items[19]["classification"] == ADVISORY_COMMITTEE
    assert parsed_items[38]["classification"] == ADVISORY_COMMITTEE


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Budget Public Hearing", FORUM),
        ("Service Councils - Meet and Confer", ADVISORY_COMMITTEE),
        ("PTSC-MTA Risk Management Authority", NOT_CLASSIFIED),
    ],
)
def test_classification_other_titles(title, expected):
    assert LoscaMetroTransitSpider()._parse_classification(title) == expected


def test_all_day(parsed_items):
    for item in parsed_items:
        assert item["all_day"] is False


def test_unique_ids(parsed_items):
    ids = [item["id"] for item in parsed_items]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize(
    "raw,expected",
    [
        (
            "Metro Board Room, 1 Gateway Plaza Hybrid in-person/virtual meeting",
            {
                "name": "Metro Board Room",
                "address": "1 Gateway Plaza, Los Angeles, CA 90012",
            },
        ),
        (
            "Marvin Braude San Fernando Valley Constituent Service Center "
            "(6262 Van Nuys Blvd, Los Angeles, Ca  91401) Hybrid in-person/virtual "
            "meeting",
            {
                "name": "Marvin Braude San Fernando Valley Constituent Service Center",
                "address": "6262 Van Nuys Blvd, Los Angeles, CA 91401",
            },
        ),
        (
            "Metro Headquarters Building\r\nOne Gateway Plaza \r\n3rd Floor Gateway "
            "Conference Room \r\nLos Angeles, CA  90012 Hybrid in-person/virtual "
            "meeting",
            {
                "name": (
                    "Metro Headquarters Building, 3rd Floor Gateway Conference Room"
                ),
                "address": HQ,
            },
        ),
        (
            "Salt Lake Park Community Center Lounge 3401 E Florence Av, Huntington "
            "Park, CA  90255/ Zoom: Webinar ID: 878 3912 9126, Passcode: 364076\r\n"
            "Salt Lake Park Community Center Lounge\r\n3401 E Florence Ave \r\n"
            "Huntington Park, CA  90255",
            {
                "name": "Salt Lake Park Community Center Lounge",
                "address": "3401 E Florence Av, Huntington Park, CA 90255",
            },
        ),
        (
            "3401 E Florence Av, Huntington Park, CA 90255 Hybrid in-person/virtual "
            "meeting",
            {
                "name": "TBD",
                "address": "3401 E Florence Av, Huntington Park, CA 90255",
            },
        ),
    ],
)
def test_location_variants(raw, expected):
    assert location_of(raw)[0] == expected


def test_zoom_details_go_to_description():
    location, description = location_of(
        "Metro Board Room, 1 Gateway Plaza, Los Angeles, 90012, Zoom Webinar "
        "ID:868 0072 4592, Passcode:764206 Hybrid in-person/virtual meeting"
    )
    assert location == {
        "name": "Metro Board Room",
        "address": "1 Gateway Plaza, Los Angeles, CA 90012",
    }
    assert description == (
        "Hybrid in-person/virtual meeting Zoom Webinar ID:868 0072 4592, "
        "Passcode:764206"
    )


@pytest.mark.parametrize(
    "raw",
    [
        "Online Virtual Meeting",
        {
            "label": "Watch online:  http://boardagendas.metro.net \r\nListen by "
            "phone: Dial 888-251-2949",
            "url": "http://boardagendas.metro.net",
        },
        "Virtual Online Meeting\r\nListen by phone: Dial +1 (877) 422-8614 "
        "Comments can be made via:\r\nPost Office Mail:\r\nOne Gateway Plaza\r\n"
        "MS: 99-3-1\r\nLos Angeles, CA 90012",
    ],
)
def test_virtual_location(raw):
    """Online-only meetings, including 2021-2022 teleconference rows that give
    only call-in details and 2020 rows whose mailing address isn't the venue."""
    assert location_of(raw)[0] == {"name": "Virtual", "address": ""}


@pytest.mark.parametrize(
    "raw,description",
    [
        (
            "Online Virtual Meeting https://zoom.us/j/123456789",
            "https://zoom.us/j/123456789",
        ),
        (
            "Zoom Webinar ID: 868 0072 4592, Passcode: 764206",
            "Zoom Webinar ID: 868 0072 4592, Passcode: 764206",
        ),
    ],
)
def test_virtual_location_keeps_access_details(raw, description):
    """Neither shape is in the live data yet: a meeting link or a Zoom ID with
    no place is a virtual meeting, and the link or ID goes to the description."""
    assert location_of(raw) == ({"name": "Virtual", "address": ""}, description)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "Hybrid in-person/virtual meeting",
        "Zoom Webinar ID:868 0072 4592 Hybrid in-person/virtual meeting",
    ],
)
def test_missing_location(raw):
    """A hybrid meeting without an address stays TBD, even with a Zoom ID."""
    assert location_of(raw)[0] == {"name": "TBD", "address": ""}


def test_unparsable_location_logs_warning(caplog):
    """caplog captures log records, so this checks that free text with no
    street address is logged and the location falls back to TBD."""
    with caplog.at_level(logging.WARNING):
        location, _ = location_of("The Service Council was formed in 2003")
    assert location == {"name": "TBD", "address": ""}
    assert "Could not parse location" in caplog.text


@pytest.fixture(scope="module")
def variant_items():
    sap_audio = {"label": "Audio", "url": "https://metro.legistar.com/Video?ID1=2"}
    events = [
        event("Construction Committee", location=HQ, meeting_id=10),
        # Posted twice in Legistar (Westside/Central Service Council 2/12/2025)
        event("South Bay Service Council", time="5:00 PM", meeting_id=20),
        event("South Bay Service Council", time="5:00 PM", meeting_id=21),
        event("Construction Committee (SAP)", meeting_id=11, Audio=sap_audio),
        event(
            "Planning and Programming Committee",
            meeting_id=40,
            **{
                "Accessible Agenda": {
                    "label": "Accessible Agenda",
                    "url": "https://metro.legistar.com/View.ashx?M=AADA&ID=40",
                },
            },
        ),
        event("Test - Live Committee Meeting Test", meeting_id=50),
        event(
            "Board of Directors - Regular Board Meeting",
            meeting_id=60,
            location="test test test",
        ),
    ]
    spider = LoscaMetroTransitSpider()
    with freeze_time("2026-03-05"):
        return list(spider.parse_legistar(events))


def test_variant_count(variant_items):
    assert [i["title"] for i in variant_items] == [
        "Construction Committee",
        "South Bay Service Council",
        "Planning and Programming Committee",
    ]


def test_spanish_audio_after_english_row(variant_items):
    assert variant_items[0]["links"][-1] == {
        "href": "https://metro.legistar.com/Video?ID1=2",
        "title": "Spanish Audio",
    }


def test_duplicate_keeps_newer_posting(variant_items):
    assert variant_items[1]["source"].endswith("ID=21")


def test_blank_time_row_is_skipped(caplog):
    """Rows with a blank time are empty placeholders (no location or agenda),
    which the original spider never output; they are skipped with a warning."""
    row = event("San Fernando Valley Service Council", date="7/31/2020", time="")
    with caplog.at_level(logging.WARNING), freeze_time("2026-03-05"):
        assert list(LoscaMetroTransitSpider().parse_legistar([row])) == []
    assert "no meeting time" in caplog.text


def test_accessible_agenda_when_no_agenda(variant_items):
    assert variant_items[2]["links"][0] == {
        "href": "https://metro.legistar.com/View.ashx?M=AADA&ID=40",
        "title": "Accessible Agenda",
    }


@pytest.mark.parametrize(
    "location,time,expected",
    [
        (
            "3401 E Florence Av, Huntington Park, CA 90255 Hybrid in-person/virtual "
            "meeting",
            "5:00 PM",
            "Please check the meeting attachment for location details.",
        ),
        (
            "",
            "Canceled",
            "Please check the meeting attachment for start time and location "
            "details.",
        ),
        (HQ + ", \r\n3rd Floor, Metro Board Room", "10:00 AM", ""),
    ],
)
def test_time_notes_for_missing_details(location, time, expected):
    """A TBD location gets a note pointing to the attachments, combined with
    the start time note when both are missing."""
    spider = LoscaMetroTransitSpider()
    row = event("Gateway Cities Service Council", time=time, location=location)
    with freeze_time("2026-03-05"):
        meeting = spider._parse_meeting(row, "Gateway Cities Service Council", {})
    assert meeting["time_notes"] == expected


def test_duplicate_prefers_active_copy():
    """A re-posted meeting next to a cancelled copy keeps the active one, even
    when the cancelled copy has more links."""
    spider = LoscaMetroTransitSpider()
    cancelled = {"status": CANCELLED, "links": [{}, {}], "source": "x?ID=21"}
    active = {"status": TENTATIVE, "links": [], "source": "x?ID=20"}
    assert max(cancelled, active, key=spider._duplicate_rank) is active


def test_sap_rows_on_later_page_are_paired():
    """Legistar pages a year's rows. Events are carried to the year's last page
    so a "(SAP)" row on another page still finds its English meeting."""
    spider = LoscaMetroTransitSpider()
    sap_audio = {"label": "Audio", "url": "https://metro.legistar.com/Video?ID1=2"}
    pages = [
        [event("Construction Committee (SAP)", meeting_id=11, Audio=sap_audio)],
        [event("Construction Committee", meeting_id=10)],
    ]
    next_page = Request(CALENDAR_URL, callback=spider._parse_legistar_events_page)
    spider._parse_legistar_events = lambda response: pages.pop(0)
    spider._parse_next_page = lambda response: iter([next_page] if pages else [])
    response = HtmlResponse(url=CALENDAR_URL, body=b"", encoding="utf-8")

    request = next(spider._parse_legistar_events_page(response))
    assert request.errback == spider._handle_error
    with freeze_time("2026-03-05"):
        meetings = list(
            spider._parse_legistar_events_page(response, **request.cb_kwargs)
        )
    assert [link["title"] for link in meetings[0]["links"]][-1] == "Spanish Audio"
    assert spider._meetings_parsed == 1


def test_empty_year_logs_warning(caplog):
    with caplog.at_level(logging.WARNING):
        assert list(LoscaMetroTransitSpider().parse_legistar([])) == []
    assert "No Legistar events found" in caplog.text


def test_unparsable_time_uses_usual_time():
    """A typo like "13:00 PM" falls back to the date, then to the committee's
    usual time, as in the original spider."""
    spider = LoscaMetroTransitSpider()
    row = event("Construction Committee", time="13:00 PM", location=HQ)
    with freeze_time("2026-03-05"):
        meeting = spider._parse_meeting(row, "Construction Committee", {})
    assert meeting["start"] == datetime(2026, 3, 4, 13, 0)


def test_missing_events_table_logs_warning(caplog):
    spider = LoscaMetroTransitSpider()
    response = HtmlResponse(url=CALENDAR_URL, body=b"<html></html>", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert spider._parse_legistar_events(response) == []
    assert "No Legistar events table" in caplog.text


def reported_errors(spider):
    """The exceptions the spider sent through Scrapy's spider_error signal,
    which scrapy_sentry_errors forwards to Sentry in production."""
    return [
        c.kwargs["failure"].value
        for c in spider.crawler.signals.send_catch_log.call_args_list
        if c.kwargs.get("signal") is signals.spider_error
    ]


def closed_spider(failed_requests=0, meetings_parsed=0, reason="finished"):
    """A spider with a mock crawler, closed after a run with these counts."""
    spider = LoscaMetroTransitSpider()
    spider.crawler = MagicMock()
    spider._failed_requests = failed_requests
    spider._meetings_parsed = meetings_parsed
    spider._on_spider_closed(spider, reason)
    return spider


def test_failed_request_is_counted_and_logged(caplog):
    spider = LoscaMetroTransitSpider()
    with caplog.at_level(logging.WARNING):
        spider._handle_error(Failure(Exception("503 Service Unavailable")))
    assert spider._failed_requests == 1
    assert "Legistar request failed" in caplog.text


def test_blocked_run_reports_one_error():
    errors = reported_errors(closed_spider(failed_requests=2))
    assert len(errors) == 1
    assert isinstance(errors[0], LoscaMetroTransitSourceError)
    assert str(errors[0]) == (
        "losca_Metro_Transit: 2 failed request(s); 0 meetings parsed "
        "(finish_reason=finished, meetings=0)"
    )


def test_good_run_reports_nothing():
    assert reported_errors(closed_spider(meetings_parsed=920)) == []


def test_requests_have_errback():
    spider = LoscaMetroTransitSpider()
    start = next(iter(spider.start_requests()))
    assert start.errback == spider._handle_error
    body = (
        b'<input name="__VIEWSTATE" value="x">'
        b'<input name="__EVENTVALIDATION" value="y">'
    )
    response = HtmlResponse(url=CALENDAR_URL, body=body, encoding="utf-8")
    with freeze_time("2026-03-05"):
        years = list(spider.parse(response))
    assert len(years) == 7
    assert all(r.errback == spider._handle_error for r in years)

import re
from datetime import datetime

import scrapy
from city_scrapers_core.constants import (
    BOARD,
    CANCELLED,
    CITY_COUNCIL,
    COMMISSION,
    COMMITTEE,
    NOT_CLASSIFIED,
)
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from dateutil.parser import parse as dateparse


class LoscaCityCouncilSpider(CityScrapersSpider):
    name = "losca_City_Council"
    agency = "Los Angeles City Council"
    timezone = "America/Los_Angeles"
    custom_settings = {"ROBOTSTXT_OBEY": False}

    source_url = "https://clerk.lacity.gov/calendar"

    portal_meeting_url = "https://lacity.primegov.com/Portal/Meeting?meetingTemplateId={template_id}"  # noqa
    upcoming_url = (
        "https://lacity.primegov.com/api/v2/PublicPortal/ListUpcomingMeetings"  # noqa
    )
    archived_url = "https://lacity.primegov.com/api/v2/PublicPortal/ListArchivedMeetings?year={year}"  # noqa

    location = {
        "name": "Office of the City Clerk",
        "address": "200 N Spring St, Room 360, Los Angeles, CA 90012",
    }

    _classification_keywords = {
        CITY_COUNCIL: "city council",
        BOARD: "board",
        COMMITTEE: "committee",
        COMMISSION: "commission",
    }

    def _has_cancellation_notice(self, links):
        for link in links or []:
            title = (link.get("title") or "").lower()
            if "cancel" in title:
                return True
        return False

    def _set_meeting_status(self, meeting):
        if self._has_cancellation_notice(meeting.get("links")):
            return CANCELLED
        return self._get_status(meeting)

    def start_requests(self):
        current_year = datetime.now().year

        for year in (current_year - 1, current_year):
            yield scrapy.Request(
                url=self.archived_url.format(year=year),
                callback=self.parse,
                meta={"type": "archived"},
            )

        yield scrapy.Request(
            url=self.upcoming_url,
            callback=self.parse,
            meta={"type": "upcoming"},
        )

    def parse(self, response):
        data = response.json()

        now = datetime.now()
        window_start = datetime(now.year - 1, 1, 1)
        window_end = datetime(now.year + 1, 12, 31, 23, 59, 59)

        for obj in data:
            start = dateparse(obj.get("dateTime"))
            if not start:
                continue
            if not (window_start <= start <= window_end):
                continue

            title = (obj.get("title") or "").strip()

            classification = self._parse_classification(title)

            if re.search(r"\bSAP\b", title, flags=re.I):
                continue

            meeting = Meeting(
                title=title,
                description="",
                classification=classification,
                start=start,
                end=None,
                all_day=False,
                time_notes="",
                location=self.location,
                links=self._parse_links(obj),
                source=self.source_url,
            )

            meeting["status"] = self._set_meeting_status(meeting)
            meeting["id"] = self._get_id(meeting)
            yield meeting

    def _parse_links(self, obj):
        links = []
        if obj.get("videoUrl"):
            links.append({"title": "Video", "href": obj["videoUrl"]})
        for doc in obj.get("documentList") or []:
            template_id = doc.get("templateId")
            compile_type = doc.get("compileOutputType")
            template_name = (doc.get("templateName") or "").strip()

            if not template_id:
                continue

            if compile_type == 3 or "html" in template_name.lower():
                links.append(
                    {
                        "title": re.sub(r"^HTML\s+", "", template_name) or "Agenda",
                        "href": self.portal_meeting_url.format(template_id=template_id),
                    }
                )
        return links

    def _parse_classification(self, title):
        """Parse meeting classification based on title keywords."""

        for classification, keyword in self._classification_keywords.items():
            if keyword in title.lower():
                return classification

        return NOT_CLASSIFIED

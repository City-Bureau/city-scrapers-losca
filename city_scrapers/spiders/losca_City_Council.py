import re
from datetime import datetime

import scrapy
from dateutil.parser import parse as dateparse

from city_scrapers_core.constants import CITY_COUNCIL, CANCELLED
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider


class LoscaCityCouncilSpider(CityScrapersSpider):
    name = "losca_city_council"
    agency = "Los Angeles City Council"
    timezone = "America/Los_Angeles"
    custom_settings = {"ROBOTSTXT_OBEY": False}

    source_url = "https://clerk.lacity.gov/calendar"

    portal_meeting_url = "https://lacity.primegov.com/Portal/Meeting?meetingTemplateId={template_id}" # noqa
    upcoming_url = "https://lacity.primegov.com/api/v2/PublicPortal/ListUpcomingMeetings" # noqa
    archived_url = "https://lacity.primegov.com/api/v2/PublicPortal/ListArchivedMeetings?year={year}" # noqa

    location = {
        "name": "Office of the City Clerk",
        "address": "200 N Spring St, Room 360, Los Angeles, CA 90012",
    }

    _CITY_COUNCIL_TITLE_RE = re.compile(
        r"(^|\b)(city council)(\b|$)", re.I
    )

    def _has_cancellation_notice(self, links):
        for link in links or []:
            title = (link.get("title") or "").lower()
            if "cancel" in title:
                return True
        return False

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

            if not self._CITY_COUNCIL_TITLE_RE.search(title):
                continue

            if re.search(r"\bSAP\b", title or "", flags=re.I):
                continue

            meeting = Meeting(
                title=title,
                description="",
                classification=CITY_COUNCIL,
                start=start,
                end=None,
                all_day=False,
                time_notes="",
                location=self.location,
                links=self._parse_links(obj),
                source=self.source_url,
            )

            if self._has_cancellation_notice(meeting.get("links")):
                meeting["status"] = CANCELLED
            else:
                meeting["status"] = self._get_status(meeting)
            meeting["id"] = self._get_id(meeting)
            yield meeting

    def _parse_links(self, obj):
        links = []
        if obj.get("videoUrl"):
            links.append({"title": "Video", "href": obj["videoUrl"]})
        for doc in (obj.get("documentList") or []):
            template_id = doc.get("templateId")
            compile_type = doc.get("compileOutputType")
            template_name = (doc.get("templateName") or "").strip()

            if not template_id:
                continue

            if compile_type == 3 or "html" in template_name.lower():
                links.append(
                    {
                        "title": template_name or "Agenda",
                        "href": self.portal_meeting_url.format(template_id=template_id),
                    }
                )
        return links

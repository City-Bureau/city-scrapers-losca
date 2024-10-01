import json

from city_scrapers_core.constants import CITY_COUNCIL
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from dateutil.parser import parse


class LoscaCityCouncilSpider(CityScrapersSpider):
    name = "losca_City_Council"
    agency = "Los Angeles City Council"
    timezone = "America/Los_Angeles"
    # original URL https://clerk.lacity.gov/calendar
    # data is shown from an iframe https://lacity.primegov.com/public/portal
    # iframe loads data from API. "scrape" API instead for upcoming
    # archived: lacity.primegov.com/api/v2/PublicPortal/ListArchivedMeetings?year=2024
    start_urls = [
        "https://lacity.primegov.com/api/v2/PublicPortal/ListUpcomingMeetings?_=1726255032697"  # noqa
    ]

    def parse(self, response):
        """
        Parse API response of upcoming meetings only.
        """

        # convert response to json
        data = json.loads(response.body)

        # hardcode location
        location = {
            "name": "Office of the City Clerk",
            "address": "200 N Spring St, Room 360, Los Angeles, CA 90012",
        }

        for obj in data:
            meeting = Meeting(
                title=obj["title"],
                description="",
                classification=CITY_COUNCIL,
                start=parse(obj["dateTime"]),
                end=None,
                all_day=False,
                time_notes="",
                location=location,
                links=self._parse_links(obj),
                source="https://clerk.lacity.gov/calendar",
            )

            meeting["status"] = self._get_status(meeting)
            meeting["id"] = self._get_id(meeting)

            yield meeting

    def _parse_links(self, obj):
        """Parse links based on given video URL."""
        links = []
        if obj.get("videoUrl"):
            links.append({"title": "video", "href": obj["videoUrl"]})
        return links

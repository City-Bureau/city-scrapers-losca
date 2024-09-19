from city_scrapers_core.constants import BOARD
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from dateutil.parser import parse


class LoscaBoardOfSupervisorsSpider(CityScrapersSpider):
    name = "losca_Board_of_Supervisors"
    agency = "Los Angeles County Board of Supervisors"
    timezone = "America/Los_Angeles"
    start_urls = ["https://bos.lacounty.gov/board-meeting-agendas/"]

    def parse(self, response):
        """Parse meeting items from agency website."""
        location = {
            "name": "Kenneth Hahn Hall of Administration",
            "address": "500 West Temple Street, Room 381B, Los Angeles",
        }
        # ".card" returns duplicates bc page has ".card"s inside .card elements
        # ".upcoming-meeting" returns the correct number of meetings even though
        # some of the meetings already happened and are not "upcoming"
        for item in response.css(".upcoming-meeting"):
            title = item.css(".card-title::text").get()
            meeting = Meeting(
                title=title,
                description="",
                classification=BOARD,
                start=self._parse_start(item),
                end=None,
                all_day=False,
                time_notes="",
                location=location,
                links=self._parse_links(item),
                source=response.url,
            )

            meeting["status"] = self._get_status(meeting)
            meeting["id"] = self._get_id(meeting)

            yield meeting

    def _parse_start(self, item):
        """
        Parse start datetime as a native datetime object.
        Combine the date with the time found in a time.
        Page says meetings start at 9:30 but one of them actually started at 11.
        Do not hardcode time when parsing.
        """
        # => 'Tuesday, September 17, 2024'
        date = item.css(".calendar-date time::text").get()

        # => '09:30 AM\n            PST'
        time = item.css(".clock-time time::text").get().split("\n")[0]

        datetime = parse(f"{date} {time}")
        return datetime

    def _parse_links(self, item):
        """
        Parse links.
        Agenda and PDF version are usually present.
        Supplemental and PDF version are sometimes present.
        Add all if found.
        """
        out = []
        links = item.css("a")
        for link in links:
            title = link.css("span::text").get()
            href = link.css("::attr(href)").get()
            out.append({"title": title, "href": href})
        return out

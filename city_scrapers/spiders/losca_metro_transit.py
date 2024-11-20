from city_scrapers_core.constants import COMMITTEE, BOARD, CITY_COUNCIL, NOT_CLASSIFIED
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import LegistarSpider


class LoscaMetroTransitSpider(LegistarSpider):
    name = "losca_metro_transit"
    agency = "Los Angeles Metro Transit"
    timezone = "America/Los_Angeles"
    start_urls = ["https://metro.legistar.com/Calendar.aspx"]
    # Add the titles of any links not included in the scraped results
    link_types = []

    def parse_legistar(self, events):
        """
        `parse_legistar` should always `yield` Meeting items.

        Change the `_parse_title`, `_parse_start`, etc methods to fit your scraping
        needs.
        """

        for event in events:
            meeting = Meeting(
                title=event.get("Name", {}).get("label", "No Title"),
                description=self._parse_description(event),
                classification=self._parse_classification(event),
                start=self.legistar_start(event),
                end=self._parse_end(event),
                all_day=self._parse_all_day(event),
                time_notes=self._parse_time_notes(event),
                location=self._parse_location(event),
                links=self._parse_links(event),
                source=self.legistar_source(event),
            )

            meeting["status"] = self._parse_status(meeting)
            meeting["id"] = self._parse_id(meeting)

            yield meeting

    def _parse_description(self, item):
        """Parse or generate meeting description."""
        return ""

    def _parse_classification(self, item):
        """Parse or generate classification from allowed options."""
        name_label = item.get("Name", {}).get("label", "").lower()
        if "committee" in name_label:
            return COMMITTEE
        if "board" in name_label:
            return BOARD
        if "council" in name_label:
            return CITY_COUNCIL
        return NOT_CLASSIFIED

    def _parse_end(self, item):
        """Parse end datetime as a naive datetime object. Added by pipeline if None"""
        return None

    def _parse_time_notes(self, item):
        """Parse any additional notes on the timing of the meeting"""
        return ""

    def _parse_all_day(self, item):
        """Parse or generate all-day status. Defaults to False."""
        return False

    def _parse_links(self, item):
        """Parse or generate links to additional information."""
        links = []

        # Parse meeting link
        if isinstance(item.get("Name"), dict) and item["Name"].get("url"):
            links.append(
                {
                    "href": item["Name"]["url"],
                    "title": item["Name"].get("label", "Meeting Details"),
                }
            )

        # Parse agenda link
        if isinstance(item.get("Agenda"), dict) and item["Agenda"].get("url"):
            links.append(
                {
                    "href": item["Agenda"]["url"],
                    "title": item["Agenda"].get("label", "Agenda"),
                }
            )

        # Parse iCalendar link
        if isinstance(item.get("iCalendar"), dict) and item["iCalendar"].get("url"):
            links.append({"href": item["iCalendar"]["url"], "title": "iCalendar"})

        # Parse audio link
        if (
            isinstance(item.get("Audio"), dict)
            and item["Audio"].get("url")
            and item["Audio"].get("label") != "Not\xa0available"
        ):
            links.append(
                {"href": item["Audio"]["url"], "title": item["Audio"]["label"]}
            )

        return links

    def _parse_location(self, item):
        """Parse or generate location."""
        if isinstance(item["Meeting Location"], dict):
            return {
                "address": item["Meeting Location"]["label"],
                "name": item["Name"]["label"],
            }
        else:
            return item["Meeting Location"]

    def _parse_status(self, item):
        if item["start"] is None:
            return "TENTATIVE"
        else:
            return self._get_status(item)

    def _parse_id(self, item):
        if item["start"] is None:
            return None
        else:
            return self._get_id(item)

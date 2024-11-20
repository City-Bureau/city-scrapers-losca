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
            print(events)
            meeting = Meeting(
                title=event["Name"]["label"],
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
        if "committee" in item["Name"]["label"].lower():
            return COMMITTEE
        if "board" in item["Name"]["label"].lower():
            return BOARD
        if "council" in item["Name"]["label"].lower():
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

        meeting_link = item["Name"]["url"]
        if meeting_link:
            links.append({
                "href": item["Name"]["url"],
                "title": item["Name"]["label"]})
        agenda_link = item["Agenda"]["url"] if isinstance(item["Agenda"], dict) else item["Agenda"]
        if isinstance(agenda_link, dict):
            links.append({
                "href": item["Agenda"]["url"],
                "title": item["Agenda"]["label"]})
        calendar_link = item["iCalendar"]["url"]
        if calendar_link:
            links.append({
                "href": item["iCalendar"]["url"],
                "title": "iCalendar"})
        audio_link = item["Audio"]
        if audio_link != "Not\xa0available":
            links.append({
                "href": item["Audio"]["url"],
                "title": item["Audio"]["label"]})

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
            self._get_status(item)

    def _parse_id(self, item):
        if item["start"] is None:
            return None
        else:
            self._get_id(item)
            
import re

from city_scrapers_core.constants import BOARD, COMMISSION, NOT_CLASSIFIED
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from dateutil.parser import parse


class LoscaCityPlanningSpider(CityScrapersSpider):
    name = "losca_city_planning"
    agency = "Los Angeles City Planning"
    timezone = "America/Los_Angeles"
    start_year = 2024
    start_urls = [
        f"https://planning.lacity.gov/dcpapi/meetings/api/all/commissions/{start_year}",
        f"https://planning.lacity.gov/dcpapi/meetings/api/all/boards/{start_year}",
        f"https://planning.lacity.gov/dcpapi/meetings/api/all/hearings/{start_year}",
    ]

    def parse(self, response):
        """
        This spider retrieves meetings for the specified `start_year`.
        Update `start_year` to change the target year.
        """
        try:
            data = response.json()
            if "Entries" not in data:
                self.logger.error("Missing 'Entries' field in response")
                return
            items = data["Entries"]
        except ValueError as e:
            self.logger.error(f"Failed to parse JSON response: {e}")
            return

        for item in items:
            if not all(key in item for key in ["Type", "Date", "Address"]):
                self.logger.warning(f"Skipping item due to missing required fields: {item}")
                continue
            meeting = Meeting(
                title=item.get("Type", ""),
                description=item.get("Note", ""),
                classification=self._parse_classification(item),
                start=parse(item.get("Date")),
                end=None,
                all_day=False,
                time_notes="",
                location=self._parse_location(item),
                links=self._parse_links(item),
                source=self._parse_source(response),
            )

            meeting["status"] = self._get_status(meeting)
            meeting["id"] = self._get_id(meeting)

            yield meeting

    def _parse_location(self, item):
        """Parse or generate location."""
        pattern = r"(\d{3,4}(?:\s?–\s?\d{3,4})?(?:\s?and\s?\d{3,4})?(?:\s?,?\s?\d{3,4})?\s[\w\s]+\b(?:Road|Drive|Boulevard|Avenue))"
        addresses = re.findall(pattern, item["Address"])
        address = ', '.join(addresses) if addresses else item.get("Address", "")
        return {
            "address": address,
            "name": item.get("BoardName", ""),
        }

    def _validate_url(self, url):
        """Validate URL format and security."""
        if not url:
            return False
        if not url.startswith('https://'):
            self.logger.warning(f"Non-HTTPS URL found: {url}")
            return False
        return True

    def _parse_links(self, item):
        """Parse or generate links."""
        links = []

        agenda_link = item.get("AgendaLink")
        if agenda_link and self._validate_url(agenda_link):
            links.append({"href": item["AgendaLink"], "title": "Agenda"})
        docs_link = item.get("AddDocsLink")
        if docs_link and self._validate_url(docs_link):
            links.append({"href": item["AddDocsLink"], "title": "Additional Documents"})

        return links

    def _parse_classification(self, item):
        lower_text = item["Type"].lower()
        if "board" in lower_text:
            return BOARD
        elif "commission" in lower_text:
            return COMMISSION
        return NOT_CLASSIFIED

    def _parse_source(self, response):
        """Parse or generate source."""
        return response.url

import re
from datetime import date

import scrapy
from city_scrapers_core.constants import BOARD
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta


class LoscaBoardOfEdSpider(CityScrapersSpider):
    name = "losca_Board_of_ed"
    agency = "Los Angeles Unified School District Board of Education"
    timezone = "America/Los_Angeles"

    # Date range configuration
    years_back = 3
    months_ahead = 3

    custom_settings = {
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
        "DOWNLOAD_HANDLERS": {
            "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
            "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        },
        "PLAYWRIGHT_BROWSER_TYPE": "firefox",
        "PLAYWRIGHT_LAUNCH_OPTIONS": {
            "headless": True,
        },
        "DOWNLOAD_DELAY": 1,
        "ROBOTSTXT_OBEY": False,
        "USER_AGENT": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:88.0) Gecko/20100101 Firefox/88.0",  # noqa
    }

    def start_requests(self):
        """Generate calendar URLs for each month in the date range."""
        today = date.today()
        start_date = today - relativedelta(years=self.years_back)
        end_date = today + relativedelta(months=self.months_ahead)

        current_date = start_date
        while current_date <= end_date:
            url = (
                f"https://boe.lausd.org/apps/events/"
                f"{current_date.year}/{current_date.month}/calendar/?id=0"
            )
            yield scrapy.Request(
                url,
                meta={
                    "playwright": True,
                    "playwright_page_methods": [
                        {
                            "method": "wait_for_selector",
                            "args": ["td.day"],
                            "kwargs": {"timeout": 10000},
                        },
                    ],
                },
                callback=self.parse,
                cb_kwargs={"year": current_date.year, "month": current_date.month},
            )
            current_date += relativedelta(months=1)

    def parse(self, response, year, month):
        """
        Parse meeting items from HTML calendar page.
        """
        # Parse all calendar days with events (exclude .extra days from adjacent months)
        for day_cell in response.css("td.day:not(.extra)"):
            day_num = day_cell.css("span.day-of-month::text").get()
            if not day_num:
                continue

            day_num = int(day_num.strip())

            # Parse each event in this day (including nested events)
            # Use XPath to get all div.event at any level
            for event in day_cell.xpath(".//div[@class='event']"):
                start = self._parse_start(event, year, month, day_num)
                end = self._parse_end(event, year, month, day_num)

                # Skip events without start time
                if start is None:
                    continue

                meeting = Meeting(
                    title=self._parse_title(event),
                    description="",
                    classification=BOARD,
                    start=start,
                    end=end,
                    all_day=False,
                    time_notes="",
                    location=self._parse_location(event),
                    links=self._parse_links(event),
                    source=response.url,
                )

                meeting["status"] = self._get_status(meeting)
                meeting["id"] = self._get_id(meeting)

                yield meeting

    def _parse_title(self, event):
        """
        Parse meeting title from event element.
        """
        # Get text from direct child a.event-title only (XPath to avoid nested events)
        title_parts = event.xpath("./a[@class='event-title']//text()").getall()
        if not title_parts:
            return self.agency
        title = " ".join(part.strip() for part in title_parts if part.strip())
        # Normalize whitespace (collapse newlines, tabs, multiple spaces)
        title = re.sub(r"\s+", " ", title).strip()
        return title if title else self.agency

    def _parse_location(self, event):
        """
        Parse location from event element.
        """
        # Get location from direct child span.event-data/span.event-location (XPath)
        location_parts = event.xpath(
            "./span[@class='event-data']/span[@class='event-location']//text()"
        ).getall()
        if location_parts:
            location_text = " ".join(
                part.strip() for part in location_parts if part.strip()
            )
            # Normalize whitespace but preserve intentional newlines
            # between address parts
            location_text = re.sub(r"[ \t]+", " ", location_text)
            location_text = re.sub(r"\n+", "\n", location_text)
            location_text = re.sub(r"\n\s+", "\n", location_text).strip().strip("()")
            return {
                "name": "",
                "address": location_text,
            }
        return {
            "name": "",
            "address": "",
        }

    def _parse_start(self, event, year, month, day):
        """
        Parse start datetime from event element.
        """
        # Get direct child span.event-data, then extract all its text
        # excluding nested events
        event_data_span = event.xpath("./span[@class='event-data']")
        if not event_data_span:
            return None

        # Get text from span.event-data, excluding text inside nested div.event elements
        # Get direct text nodes + text from children that aren't div.event
        time_parts = (
            event_data_span[0]
            .xpath("./text() | ./*[not(self::div[@class='event'])]//text()")
            .getall()
        )
        if not time_parts:
            return None

        event_data = " ".join(part.strip() for part in time_parts if part.strip())
        if not event_data:
            return None

        # Extract start time (format: "10 AM", "3:30 PM", etc.)
        time_match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*([AP]M)", event_data)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2)) if time_match.group(2) else 0
            meridiem = time_match.group(3)

            # Convert to 24-hour format
            if meridiem == "PM" and hour != 12:
                hour += 12
            elif meridiem == "AM" and hour == 12:
                hour = 0

            date_str = f"{month}/{day}/{year} {hour}:{minute:02d}"
            return parse(date_str)

        return None

    def _parse_end(self, event, year, month, day):
        """
        Parse end datetime from event element.
        """
        # Get direct child span.event-data, then extract all its text
        # excluding nested events
        event_data_span = event.xpath("./span[@class='event-data']")
        if not event_data_span:
            return None

        # Get text from span.event-data, excluding text inside nested div.event elements
        # Get direct text nodes + text from children that aren't div.event
        time_parts = (
            event_data_span[0]
            .xpath("./text() | ./*[not(self::div[@class='event'])]//text()")
            .getall()
        )
        if not time_parts:
            return None

        event_data = " ".join(part.strip() for part in time_parts if part.strip())
        if not event_data:
            return None

        # Extract end time after the dash (format: "– 2 PM", "– 5:30 PM", etc.)
        time_match = re.search(r"–\s*(\d{1,2})(?::(\d{2}))?\s*([AP]M)", event_data)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2)) if time_match.group(2) else 0
            meridiem = time_match.group(3)

            # Convert to 24-hour format
            if meridiem == "PM" and hour != 12:
                hour += 12
            elif meridiem == "AM" and hour == 12:
                hour = 0

            date_str = f"{month}/{day}/{year} {hour}:{minute:02d}"
            return parse(date_str)

        return None

    def _parse_links(self, event):
        """
        Parse links from event element.
        """
        # Get href from direct child a.event-title (XPath for consistency)
        href = event.xpath("./a[@class='event-title']/@href").get()
        if not href:
            return []

        # Extract actual URL from javascript:openLink() call
        url_match = re.search(r"openLink\('([^']+)'\)", href)
        if url_match:
            url = url_match.group(1)
            # Make absolute URL
            if url.startswith("/"):
                url = f"https://boe.lausd.org{url}"
            return [{"title": "Meeting Details", "href": url}]

        return []

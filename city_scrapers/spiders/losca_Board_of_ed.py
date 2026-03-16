import re
from datetime import date

import scrapy
from city_scrapers_core.constants import BOARD, COMMITTEE
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta


class LoscaBoardOfEdSpider(CityScrapersSpider):
    name = "losca_Board_of_ed"
    agency = "Los Angeles Unified School District Board of Education"
    timezone = "America/Los_Angeles"

    # Date range configuration
    years_back = 1
    months_ahead = 1

    location = {
        "name": "LAUSD Headquarters",
        "address": "333 South Beaudry Avenue, Board Room, Los Angeles, CA 90017",
    }

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
        "FEED_EXPORT_ENCODING": "utf-8",
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

                title = self._parse_title(event)

                meeting = Meeting(
                    title=title,
                    description="",
                    classification=self._parse_classification(title),
                    start=start,
                    end=end,
                    all_day=False,
                    time_notes="",
                    location=self.location,
                    links=self._parse_links(event),
                    source=response.url,
                )

                meeting["status"] = self._get_status(meeting)
                meeting["id"] = self._get_id(meeting)

                yield meeting
                title = self._parse_title(event)
                cleaned_title = self._clean_title(title)

                meeting = Meeting(
                    title=cleaned_title,
                    description="",
                    classification=self._parse_classification(title),
                    start=start,
                    end=end,
                    all_day=False,
                    time_notes="",
                    location=self.location,
                    links=self._parse_links(event),
                    source=response.url,
                )

                meeting["status"] = self._get_status(meeting, text=title)
                meeting["id"] = self._get_id(meeting)

                yield meeting

    def _normalize_title(self, title):
        title = re.sub(r"^(CANCELED|CANCELLED|RESCHEDULED)\s*(-\s*)?", "", title, flags=re.IGNORECASE).strip()
        
        match = re.search(r"\bto\b.+?(?:-+)\s*(.+)", title, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
        match = re.search(r"^(.*?),?\s*\bto\b.+\b(?:am|pm)\b\s*(.+)", title, flags=re.IGNORECASE)
        if match:
            return match.group(2).strip()
        
        return title
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
        title = title.replace("RE-SCHEDULED", "RESCHEDULED")
        return title if title else self.agency

    def _parse_classification(self, title):
        """
        Parse meeting classification from title.
        """
        if "committee" in title.lower():
            return COMMITTEE
        return BOARD

    def _get_event_data_text(self, event):
        """Extracts and cleans text from the event data span, excluding nested events."""
        event_data_span = event.xpath("./span[@class='event-data']")
        if not event_data_span:
            return None

        # Get text from span.event-data, excluding text inside nested div.event elements
        time_parts = (
            event_data_span[0]
            .xpath("./text() | ./*[not(self::div[@class='event'])]//text()")
            .getall()
        )
        if not time_parts:
            return None

        event_data = " ".join(part.strip() for part in time_parts if part.strip())
        return event_data if event_data else None

    def _parse_start(self, event, year, month, day):
        """
        Parse start datetime from event element.
        """
        event_data = self._get_event_data_text(event)
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
        event_data = self._get_event_data_text(event)
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

import re
from collections import defaultdict
from datetime import time

import scrapy
from city_scrapers_core.constants import (
    ADVISORY_COMMITTEE,
    BOARD,
    CANCELLED,
    COMMITTEE,
    FORUM,
    NOT_CLASSIFIED,
)
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import LegistarSpider
from scrapy import signals
from twisted.python.failure import Failure


class LoscaMetroTransitSourceError(Exception):
    """Raised at close when Legistar requests failed or no meetings were parsed."""


class LoscaMetroTransitSpider(LegistarSpider):
    name = "losca_Metro_Transit"
    agency = "Los Angeles Metro Transit"
    timezone = "America/Los_Angeles"
    start_urls = ["https://metro.legistar.com/Calendar.aspx"]
    # "Accessible Agenda" is an alternate copy of the agenda, so it is only
    # added when a meeting has no regular agenda (see _parse_links).
    link_types = ["Agenda Packet", "Meeting Details", "Audio"]

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "FEED_EXPORT_ENCODING": "utf-8",
    }

    time_notes_missing = "Please check the meeting attachment for {details} details."
    hq_city_state_zip = "Los Angeles, CA 90012"

    sap_re = re.compile(r"\s*\(SAP\)\s*$", re.IGNORECASE)
    test_re = re.compile(r"\btest\b", re.IGNORECASE)
    # Text from these markers on is call-in/comment info, not the location
    details_re = re.compile(
        r"Watch online|Listen by phone|Comments can be made|To give written",
        re.IGNORECASE,
    )
    virtual_re = re.compile(r"^(?:online|virtual)\b", re.IGNORECASE)
    hybrid_re = re.compile(r"\bHybri\w*\s+in[- ]?pe\w*\s*/\s*v\w*\s+meeting\b", re.I)
    zoom_re = re.compile(
        r"(?:Zoom:?\s*)?(?:Webinar|Zoom)\s+ID\s*:?\s*[\d\s]+#?"
        r"(?:,?\s*(?:Passcode|Pa\w*cipant\s+(?:ID|Code))\s*:?\s*\d+#?)?",
        re.IGNORECASE,
    )
    # A meeting link written in the location itself, e.g. a Zoom join URL
    url_re = re.compile(r"https?://\S+", re.IGNORECASE)
    street_re = re.compile(r"^(?:\d{1,5}|One)\s+[A-Za-z]")
    # A room written after the street in the same part, e.g.
    # "1 Gateway Plaza 3rd Floor Gateway Conference Room"
    street_room_re = re.compile(r"\s+(?=\d+(?:st|nd|rd|th)\s+Fl)", re.IGNORECASE)
    state_zip_re = re.compile(r"^(?:(CA|California)\.?)?\s*(\d{4,6})?$", re.IGNORECASE)
    state_before_name_re = re.compile(r"\b(CA)\s+(?=[A-Z][a-z])")
    # A street number right after a name with no comma, e.g. "Lounge 3401 E"
    name_before_street_re = re.compile(r"(?<=[a-z])\s+(?=\d{3,5}\s+[A-Z])")
    cross_street_re = re.compile(r"\([^)]*&[^)]*\)")
    room_re = re.compile(
        r"\b(?:floor|fl|room|rm|building|hall|center|lounge|inn|stadium|hub|"
        r"college|arboretum|headquarters|division\s*\d+|conference|council)\b",
        re.IGNORECASE,
    )
    hq_re = re.compile(r"^(?:1|One)\s+Gateway\s+Plaza\b", re.IGNORECASE)
    forum_re = re.compile(r"\bhearing\b", re.IGNORECASE)
    advisory_re = re.compile(r"\bservice councils?\b|\badvisory\b", re.IGNORECASE)
    committee_re = re.compile(r"\bcommittee\b", re.IGNORECASE)
    board_re = re.compile(r"\bboard\b", re.IGNORECASE)
    legistar_id_re = re.compile(r"[?&]ID=(\d+)")

    # Cancelled meetings have "Canceled" instead of a time, so they get the
    # committee's usual start time. Kept as in the original spider because
    # changing these times changes meeting ids already published downstream.
    agencies_start_time = {
        "Board of Directors - Regular Board Meeting": time(10, 0),
        "Operations, Safety, and Customer Experience Committee": time(13, 0),
        "Executive Management Committee": time(11, 0),
        "Finance, Budget and Audit Committee": time(10, 0),
        "Planning and Programming Committee": time(11, 0),
        "Ad Hoc Board Composition Committee": time(13, 0),
        "Construction Committee": time(13, 0),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.since_year = 2020
        self._failed_requests = 0
        self._meetings_parsed = 0

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider._on_spider_closed, signal=signals.spider_closed)
        return spider

    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(url, callback=self.parse, errback=self._handle_error)

    def parse(self, response):
        """Request each year from since_year on, with an errback added to the
        core Legistar year requests."""
        for request in super().parse(response):
            yield request.replace(errback=self._handle_error)

    def _parse_legistar_events_page(self, response, events=None):
        """Legistar splits a year into pages, and a "(SAP)" row can be on a
        different page than its English meeting. Events are carried along the
        page chain and parsed together once the year's last page is read."""
        events = (events or []) + self._parse_legistar_events(response)
        next_pages = list(self._parse_next_page(response))
        if next_pages:
            yield next_pages[0].replace(
                cb_kwargs={"events": events}, errback=self._handle_error
            )
            return
        yield from self.parse_legistar(events)

    def _handle_error(self, failure):
        """A failed Legistar request means missing meetings. It is counted and
        reported once when the spider closes."""
        self._failed_requests += 1
        self.logger.warning("Legistar request failed: %r", failure.value)

    def _on_spider_closed(self, spider, reason):
        """Report one error per run if requests failed or no meetings were
        found, so a blocked run doesn't finish as a quiet success with 0
        meetings. Follows City-Bureau/city-scrapers-colgo#39."""
        problems = []
        if self._failed_requests:
            problems.append(f"{self._failed_requests} failed request(s)")
        if reason == "finished" and self._meetings_parsed == 0:
            problems.append("0 meetings parsed")
        if not problems:
            return
        self._report_error(
            LoscaMetroTransitSourceError(
                f"{self.name}: {'; '.join(problems)} "
                f"(finish_reason={reason}, meetings={self._meetings_parsed})"
            )
        )

    def _report_error(self, exc):
        """Report an error outside a callback the way Scrapy reports callback
        errors: ERROR log, spider_exceptions stat, and the spider_error signal
        that scrapy_sentry_errors forwards to Sentry."""
        self.logger.error(str(exc))
        self.crawler.stats.inc_value(
            f"spider_exceptions/{exc.__class__.__name__}", spider=self
        )
        self.crawler.signals.send_catch_log(
            signal=signals.spider_error,
            failure=Failure(exc),
            response=None,
            spider=self,
        )

    def parse_legistar(self, events):
        if not events:
            # Every year since since_year has meetings, so no rows at all means
            # the calendar page changed or came back empty
            self.logger.warning("No Legistar events found for a requested year")
            return
        events = [e for e in events if not self._is_test(e)]
        spanish_audio = self._parse_spanish_audio(events)
        meetings = {}
        for event in events:
            title = self._clean_text(self._event_title(event))
            if self.sap_re.search(title):
                continue
            meeting = self._parse_meeting(event, title, spanish_audio)
            if meeting is None:
                continue
            current = meetings.get(meeting["id"])
            if current is None:
                meetings[meeting["id"]] = meeting
                continue
            # Legistar sometimes posts the same meeting twice. Keep the active
            # copy, then the one with more links, then the newer posting, so
            # the output doesn't depend on row order.
            kept = max(current, meeting, key=self._duplicate_rank)
            self.logger.warning(
                "Duplicate meeting %s in source; keeping %s",
                meeting["id"],
                kept["source"],
            )
            meetings[meeting["id"]] = kept
        self._meetings_parsed += len(meetings)
        yield from meetings.values()

    def _parse_start(self, event, title):
        """The original spider's start parsing: Legistar's date and time, or
        the date alone when the time is a status like "Canceled", with the
        committee's usual time filled in for those."""
        try:
            start = self.legistar_start(event)
        except ValueError:
            self.logger.warning(
                "Skipping %r: unparsable date %r", title, event.get("Meeting Date")
            )
            return None
        if start is None:
            # Rows with a blank time are empty placeholders (no location or
            # agenda either), which the original spider never output
            self.logger.warning(
                "Skipping %r on %s: no meeting time",
                title,
                event.get("Meeting Date"),
            )
            return None
        if start.hour == 0 and start.minute == 0:
            usual = self.agencies_start_time.get(title)
            if usual:
                start = start.replace(hour=usual.hour, minute=usual.minute)
        return start

    def _parse_meeting(self, event, title, spanish_audio):
        start = self._parse_start(event, title)
        if start is None:
            return None
        missing = []
        if start.hour == 0 and start.minute == 0:
            self.logger.warning(
                "No start time for %r on %s (%r)",
                title,
                start.date(),
                event.get("Meeting Time"),
            )
            missing.append("start time")
        location, description = self._parse_location(event)
        if location["name"] == "TBD":
            missing.append("location")
        time_notes = (
            self.time_notes_missing.format(details=" and ".join(missing))
            if missing
            else ""
        )
        links = self._parse_links(event)
        audio = spanish_audio.get(self._pair_key(event, title))
        if audio:
            links.append({"href": audio, "title": "Spanish Audio"})
        meeting = Meeting(
            title=title,
            description=description,
            classification=self._parse_classification(title),
            start=start,
            end=None,
            all_day=False,
            time_notes=time_notes,
            location=location,
            links=links,
            source=self._parse_source(event),
        )
        meeting["status"] = self._get_status(
            meeting, text=event.get("Meeting Time") or ""
        )
        meeting["id"] = self._get_id(meeting)
        return meeting

    def _event_title(self, event):
        name = event.get("Name")
        if isinstance(name, dict):
            return name.get("label") or ""
        return name or ""

    def _is_test(self, event):
        """Legistar has test meetings, marked in the title or in the location."""
        location = event.get("Meeting Location") or ""
        if isinstance(location, dict):
            location = location.get("label") or ""
        return bool(
            self.test_re.search(self._event_title(event))
            or self.test_re.fullmatch(location.split()[0] if location.split() else "")
        )

    def _pair_key(self, event, title):
        """Key that pairs a "(SAP)" Spanish row with its English meeting."""
        return (
            self.sap_re.sub("", title).strip(),
            event.get("Meeting Date"),
            event.get("Meeting Time"),
        )

    def _parse_spanish_audio(self, events):
        """Map each "(SAP)" row's audio to the English meeting with the same
        title, date and time."""
        english_keys = set()
        sap_audio = {}
        for event in events:
            title = self._clean_text(self._event_title(event))
            key = self._pair_key(event, title)
            if not self.sap_re.search(title):
                english_keys.add(key)
                continue
            audio = event.get("Audio")
            if isinstance(audio, dict) and audio.get("url"):
                sap_audio[key] = audio["url"]
        for key in sap_audio.keys() - english_keys:
            self.logger.warning("Spanish audio with no English meeting: %r", key)
        return sap_audio

    def _duplicate_rank(self, meeting):
        match = self.legistar_id_re.search(meeting["source"])
        return (
            meeting["status"] != CANCELLED,
            len(meeting["links"]),
            int(match.group(1)) if match else 0,
        )

    def _parse_links(self, event):
        links = self.legistar_links(event)
        titles = {link["title"] for link in links}
        accessible = event.get("Accessible Agenda")
        if (
            "Agenda" not in titles
            and isinstance(accessible, dict)
            and accessible.get("url")
        ):
            links.insert(0, {"href": accessible["url"], "title": "Accessible Agenda"})
        return links

    def _parse_source(self, event):
        """Each meeting's own Legistar detail page, or the calendar."""
        details = event.get("Meeting Details")
        if isinstance(details, dict) and details.get("url"):
            return details["url"]
        return self.start_urls[0]

    def _parse_legistar_events(self, response):
        events_table = response.css("table.rgMasterTable")
        if not events_table:
            self.logger.warning("No Legistar events table on %s", response.url)
            return []
        events_table = events_table[0]

        headers = []
        for header in events_table.css("th[class^='rgHeader']"):
            header_text = (
                " ".join(header.css("*::text").extract()).replace("&nbsp;", " ").strip()
            )
            header_inputs = header.css("input")
            if header_text:
                headers.append(header_text)
            elif len(header_inputs) > 0:
                headers.append(header_inputs[0].attrib["value"])
            else:
                headers.append(header.css("img")[0].attrib["alt"])

        events = []
        for row in events_table.css("tr.rgRow, tr.rgAltRow"):
            try:
                data = defaultdict(lambda: None)
                for header, field in zip(headers, row.css("td")):
                    field_text = (
                        " ".join(field.css("*::text").extract())
                        .replace("&nbsp;", " ")
                        .strip()
                    )
                    url = None
                    if len(field.css("a")) > 0:
                        link_el = field.css("a")[0]
                        if "onclick" in link_el.attrib and link_el.attrib[
                            "onclick"
                        ].startswith(("radopen('", "window.open", "OpenTelerikWindow")):
                            url = response.urljoin(
                                link_el.attrib["onclick"].split("'")[1]
                            )
                        elif "href" in link_el.attrib:
                            url = response.urljoin(link_el.attrib["href"])
                    if url:
                        if "View.ashx?M=IC" in url:
                            header = "iCalendar"
                            value = {"url": url}
                        else:
                            value = {"label": field_text, "url": url}
                    else:
                        value = field_text

                    data[header] = value

                ical_url = (data.get("iCalendar") or {}).get("url")
                if ical_url is None:
                    self.logger.warning("Skipping Legistar row with no iCalendar link")
                    continue
                if ical_url in self._scraped_urls:
                    continue
                self._scraped_urls.add(ical_url)
                events.append(dict(data))
            except Exception as e:
                self.logger.warning("Could not parse Legistar row: %s", e)

        return events

    def _parse_classification(self, title):
        if self.forum_re.search(title):
            return FORUM
        if self.advisory_re.search(title):
            return ADVISORY_COMMITTEE
        if self.committee_re.search(title):
            return COMMITTEE
        if self.board_re.search(title):
            return BOARD
        return NOT_CLASSIFIED

    def _clean_text(self, text):
        """Normalize unicode characters in text (e.g. curly quotes, accented chars)."""
        if not text:
            return text
        text = text.replace("’", "'").replace("‘", "'")
        text = text.replace("“", '"').replace("”", '"')
        return text.strip()

    def _squash(self, text):
        return " ".join(text.split())

    def _parse_location(self, event):
        """Split the Meeting Location column into the location and the
        description. The column is free text: building and room names before
        or after the street, call-in and Zoom details, and a "Hybrid
        in-person/virtual meeting" note. Returns (location, description)."""
        raw = event.get("Meeting Location") or ""
        if isinstance(raw, dict):
            raw = raw.get("label") or ""
        raw = self._clean_text(raw.replace("\r", ""))

        details = ""
        match = self.details_re.search(raw)
        if match:
            raw, details = raw[: match.start()], raw[match.start() :]
        # Meeting links and Zoom IDs are access details: keep them in the
        # description so a virtual meeting doesn't lose its joining link
        notes = [m.group(0) for m in self.url_re.finditer(raw)]
        raw = self.url_re.sub(" ", raw)
        notes += [m.group(0) for m in self.zoom_re.finditer(raw)]
        raw = self.zoom_re.sub(" ", raw)
        hybrid = self.hybrid_re.search(raw)
        if hybrid:
            notes.insert(0, hybrid.group(0))
            raw = raw[: hybrid.start()] + raw[hybrid.end() :]
        description = self._squash(" ".join(notes + [details]))

        text = self._squash(raw)
        if self.virtual_re.match(text):
            return {"name": "Virtual", "address": ""}, description
        location = self._parse_address(raw)
        if location is None and (details or notes) and not hybrid:
            # Only call-in, Zoom or link details, no place: the 2021-2023
            # teleconference meetings, whose agendas also list only online and
            # phone access. A hybrid meeting without an address stays TBD.
            return {"name": "Virtual", "address": ""}, description
        if location is None:
            if text:
                self.logger.warning("Could not parse location %r", text)
            return {"name": "TBD", "address": ""}, description
        return location, description

    def _parse_address(self, text):
        """Find the street part, then sort the other parts into the name
        (building, room) and the rest of the address (city, state, ZIP).
        Returns None when there is no street address."""
        text = self.cross_street_re.sub("", text)
        text = text.replace("(", ",").replace(")", ",")
        text = re.sub(r"[:\n]|\.\s+(?=\d)", ",", text)
        text = self.state_before_name_re.sub(r"\1, ", text)
        text = self.name_before_street_re.sub(", ", text)
        text = re.sub(r"\s*(?:/|\bor\b)\s*$", "", text.strip())
        parts = []
        for part in text.split(","):
            part = self._squash(part).strip(" ,/")
            if part and part.lower() not in (p.lower() for p in parts):
                parts.append(part)

        street_index = next(
            (i for i, p in enumerate(parts) if self.street_re.match(p)), None
        )
        if street_index is None:
            return None
        street, *room = self.street_room_re.split(parts[street_index], maxsplit=1)
        names = parts[:street_index] + room
        city = state = zip_code = ""
        for part in parts[street_index + 1 :]:
            state_zip = self.state_zip_re.match(part)
            if state_zip and part:
                state = state or (state_zip.group(1) or "").upper()
                zip_code = zip_code or state_zip.group(2) or ""
            elif part.lower() == "united states" or self.street_re.match(part):
                # A second copy of the street, when the source repeats itself
                continue
            elif self.room_re.search(part) or re.match(r"\d+(st|nd|rd|th)\b", part):
                names.append(part)
            elif not city:
                city = part
            else:
                names.append(part)

        if self.hq_re.match(street) and not (state and zip_code):
            address = f"{street}, {self.hq_city_state_zip}"
        else:
            state_zip = " ".join(p for p in (state, zip_code) if p)
            address = ", ".join(p for p in (street, city, state_zip) if p)
        # A row with only a street address keeps name TBD: venue names for the
        # same address change over time and can't be verified per meeting
        return {"name": ", ".join(names) or "TBD", "address": address}

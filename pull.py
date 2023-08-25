# IG we're using selenium now
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.common.exceptions import NoSuchElementException
from urllib.parse import unquote
from concurrent.futures import ThreadPoolExecutor
from ics import Calendar, Event  # type: ignore
from bs4 import BeautifulSoup as BS
import functools
from typing import TypeAlias, Any
from enum import StrEnum
from dataclasses import dataclass


# Set to none to use default ThreadPoolExecutor quantity
MAX_WORKERS = 20


class Audience(StrEnum):
    FIRST_YEAR = "First-Year"
    SECOND_YEAR = "Second-Year"
    EXCHANGE_IGSP = "Exchange/IGSP"
    FGLI = "FGLI"
    INTERNATIONAL = "International"
    TRANSFER = "Transfer"
    ANY = "ANY"


@dataclass
class RawEvent:
    audience: set[Audience]
    link: str
    cal_str: str
    loc_name: str | None
    loc_addr: str | None
    mandatory: bool | None


# Set up firefox options
options = Options()
options.add_argument("--headless")  # type: ignore

browser = webdriver.Firefox(options)
browser.get("https://nso.upenn.edu/events/events-calendar/")
assert "Events Calendar" in browser.title

# Find all the links to events
EventRecord: TypeAlias = tuple[str, set[Audience]]
event_links: list[EventRecord] = []

for event_anchor in browser.find_elements(By.XPATH, "//a [@rel='bookmark']"):
    # Event type is stored as an anchor element under the ancestor of the event link.
    event_type_urls = event_anchor.find_elements(  # type: ignore
        By.XPATH, ".//ancestor::li//ul [@class='event-badges']/li/a"
    )  # type:ignore
    # Extract the intended audience from the tags
    event_type = {Audience(url.accessible_name) for url in event_type_urls} or {
        Audience.ANY
    }
    event_links.append((event_anchor.get_attribute("href"), event_type))  # type: ignore

Entry: TypeAlias = tuple[Event, set[Audience]]


def get_raw_event(record: EventRecord) -> RawEvent:
    link, audience = record
    audience = audience or {Audience.ANY}

    browser = webdriver.Firefox(options)
    browser.get(link)
    x = browser.find_element(By.XPATH, "//a [@id='apple-calendar-link']")
    # Remove the mime type info and url decode.
    cal_content = unquote(x.get_attribute("href")).split(",", 1)[1]  # type: ignore

    # Extract all calendar data.
    try:
        loc_name = browser.find_element(
            By.XPATH, "//div [@class='location-title']"
        ).text
    except NoSuchElementException:
        loc_name = None

    try:
        browser.find_element(By.XPATH, "//div [@class='mandatory-badge']")
        mandatory = True

    except NoSuchElementException:
        mandatory = False

    try:
        loc_address = " ".join(
            browser.find_element(By.XPATH, "//div [@id='location-address']")
            .text.strip()
            .splitlines()
            # Remove prefix caused by screen reader text.
        ).removeprefix("Address for")
    except NoSuchElementException:
        loc_address = None

    browser.close()
    raw_event = RawEvent(audience, link, cal_content, loc_name, loc_address, mandatory)
    return raw_event


def process_event(record: RawEvent) -> Entry | None:
    # Needed as ical library doesn't allow ommitting PROD ID
    cal_content = record.cal_str.splitlines()
    cal_content.insert(1, "PRODID:NSO_CAL")

    # Cause whoever at NSO wrote this can't write ical's for shit and the end date is
    # sometimes the epoch time.
    try:
        event = Calendar("\n".join(cal_content)).events.pop()
    except ValueError:
        print(f"Entry with url {record.link} has malformed date information")
        return
    except KeyError:
        print(f"Entry with url {record.link} did not contain any calendar entries")
        return

    # Process location
    match (record.loc_name, record.loc_addr):
        case (None, None):
            event.location = ""
        case (None, addr):
            event.location = addr
        case (name, None):
            event.location = name
        case (name, addr):
            event.location = f"{record.loc_name}: {record.loc_addr}."

    # Add mandatory flag if applicable
    if record.mandatory:
        event.name = f"MANDATORY: {event.name}"

    # Parse description
    unchecked_description = event.description
    event.description = f"Intended audience: {' '.join(record.audience)}"
    if unchecked_description is not None:
        parsed_description = BS(
            unchecked_description, "html.parser"
        ).text.strip()  # For some reason we get unformatted html in the text. Thanks NSO  # noqa: E501
        event.description += f"\n\n{parsed_description}"
    event.url = record.link
    return (event, record.audience)


def collect_raw_entries() -> list[RawEvent]:
    """Collects the raw entries for processing later.
    Allows for processing to occur in a different cell.

    Returns:
        list[RawEvent|None]: List of raw events.
    """
    executor = ThreadPoolExecutor(MAX_WORKERS)
    return [x for x in executor.map(get_raw_event, event_links)]


# This takes a while, don't worry if it's taking a long time.
raw_entries = collect_raw_entries()
calendar = [processed for record in raw_entries if (processed := process_event(record))]


def __reduction_function(cal: Calendar, event: tuple[Event, Any]):
    cal.events.add(event[0])
    return cal


def reduce_cal(cal_list: list[Entry]) -> Calendar:
    # This order matters for some reason, normally could have Calendar() as the initial
    # parameter in the fold.
    calendar = Calendar()
    calendar.method = "REQUEST"  # type: ignore
    calendar = functools.reduce(__reduction_function, iter(cal_list), calendar)
    return calendar


def create_cal(cal_list: list[Entry], predicates: set[Audience]) -> Calendar:
    events = [entry for entry in cal_list if predicates.intersection(entry[1])]
    return reduce_cal(events)


# Calendar with all events
general_calendar = reduce_cal(calendar)
with open("./output_calendars/general_calendar.ics", "w") as file:
    file.writelines(general_calendar.serialize_iter())


# Calendar for exchange students only
exchange_calendar = create_cal(calendar, {Audience.EXCHANGE_IGSP, Audience.ANY})
with open("./output_calendars/exchange_igsp_events.ics", "w") as file:
    file.writelines(exchange_calendar.serialize_iter())

transfer_calendar = create_cal(calendar, {Audience.TRANSFER, Audience.ANY})
with open("./output_calendars/transfer_events.ics", "w") as file:
    file.writelines(transfer_calendar.serialize_iter())

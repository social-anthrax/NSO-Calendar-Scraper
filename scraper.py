# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.15.1
#   kernelspec:
#     display_name: nso-calendar-scraper-bsvHhkZW-py3.11
#     language: python
#     name: python3
# ---

# %%
# IG we're using selenium now
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.common.exceptions import NoSuchElementException

from bs4 import BeautifulSoup as BS
from urllib.parse import unquote
from concurrent.futures import ThreadPoolExecutor
from ics import Calendar, Event
import functools
from typing import TypeAlias, Any
from enum import StrEnum
from dataclasses import dataclass
import zoneinfo
from datetime import datetime, timedelta
import itertools


# Set to none to use default ThreadPoolExecutor quantity
MAX_WORKERS = 20
TZ = zoneinfo.ZoneInfo("America/New_York")


# %%
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
    # If the cal entry is broken, fall back to parsing this.
    text_time: str | None
    text_date: str | None


# %%
# Set up firefox options
options = Options()
options.add_argument("--headless")  # type: ignore

# %%
browser = webdriver.Firefox(options)
browser.get("https://nso.upenn.edu/events/events-calendar/")
assert "Events Calendar" in browser.title

# %%
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
    # "//ul [@class='event-badges']"
event_links


# %%
# Define all parsers
def _parse_date(str_date: str):
    """Extracts date from NSO calendar website.
    Assumes that format follows "

    Args:
        str_date (str): _description_

    Returns:
        _type_: _description_
    """
    parsed = str_date.splitlines()[1]
    dt_date = datetime.strptime(parsed, "%A, %B %d, %Y").date()
    return dt_date


def parse_time(str_time: str):
    split = str_time.splitlines()

    t_start = datetime.strptime(
        split[1].rstrip().removesuffix("-").strip(), "%I:%M %p"
    ).time()
    t_end = datetime.strptime(split[-1].strip(), "%I:%M %p").time()
    return t_start, t_end


def parse_datetime(str_date: str, str_time: str):
    dt_date = _parse_date(str_date)
    t_start, t_end = parse_time(str_time)

    dt_start = datetime.combine(dt_date, t_start)

    if t_start > t_end:
        dt_end = datetime.combine(dt_date + timedelta(days=1), t_end)
    else:
        dt_end = datetime.combine(dt_date, t_end)

    return dt_start, dt_end


def __format_datetime(dt: datetime):
    # Don't add a Z at the end as we're not using UTC when we add a time zone.
    return dt.strftime("%Y%m%dT%H%M%S")


def fix_time(cal_content: list[str], dt_start: datetime, dt_end: datetime):
    """Corrects

    Args:
        cal_content (list[str]): _description_
        dt_start (datetime): _description_
        dt_end (datetime): _description_

    Returns:
        _type_: _description_
    """
    iterator = enumerate(cal_content)
    # This solution is a bit janky, but the NSO calendar is always formatter to have start before end,
    # this technically isn't a guarantee by the RFC but it works for now
    start_index, _ = next(x for x in iterator if x[1].startswith("DTSTART:"))
    end_index, _ = next(x for x in iterator if x[1].startswith("DTEND:"))
    # Add the time zone info
    cal_content[start_index] = f"DTSTART;TZID={str(TZ)}:{__format_datetime(dt_start)}"
    cal_content[end_index] = f"DTEND;TZID={str(TZ)}:{__format_datetime(dt_end)}"
    ret = "\n".join(cal_content)
    return ret


def inject_tz_info(cal_content: list[str]) -> list[str]:
    """Currently unused. fixes up existing time zones using TZID in the DTSTART and DTEND.
    Assumes calendar times are already set to `TZ`, which isn't the case with the NSO cal

    Args:
        cal_content (list[str]): ICS file as a string split into lines

    Returns:
        list[str]: Returns the ICS file with the string split into lines.
    """
    iterator = enumerate(cal_content)
    start_index, dtstart_content = next(
        x for x in iterator if x[1].startswith("DTSTART:")
    )
    end_index, dtend_content = next(x for x in iterator if x[1].startswith("DTEND:"))

    def add_tz(line: str):
        dt_type, timestamp = line.rstrip("Z").split(":", 1)
        return f"{dt_type};TZID={str(TZ)}:{timestamp}"

    cal_content[start_index] = add_tz(dtstart_content)
    cal_content[end_index] = add_tz(dtend_content)
    return cal_content


# %%
# Define helper functions
from typing import Generator, TypeVar


T = TypeVar('T')
def batch(iterable: list[T], size: int) -> Generator[T, None, None]:
    it = iter(iterable)
    while item := list(itertools.islice(it, size)):
        yield item # type: ignore



# %%
Entry: TypeAlias = tuple[Event, set[Audience]]


def batched_fetch_raw_event(record_list: list[EventRecord]) -> list[RawEvent]:
    with webdriver.Firefox(options) as browser:
        raw_event_list = [
            get_raw_event(browser, event_record) for event_record in record_list
        ]

    return raw_event_list


def get_raw_event(browser: webdriver.Firefox, record: EventRecord) -> RawEvent:
    link, audience = record
    audience = audience or {Audience.ANY}

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

    try:
        text_time = browser.find_element(
            By.XPATH, "//*[@id='single-events-top']/div[1]/p[2]"
        ).text.strip()
    except:
        text_time = None

    try:
        text_date = browser.find_element(
            By.XPATH, '//*[@id="single-events-top"]/div[1]/p[1]'
        ).text
    except:
        text_date = None

    raw_event = RawEvent(
        audience,
        link,
        cal_content,
        loc_name,
        loc_address,
        mandatory,
        text_time,
        text_date,
    )
    return raw_event


def process_event(record: RawEvent) -> Entry | None:
    # Needed as ical library doesn't allow ommitting PROD ID
    cal_content = record.cal_str.splitlines()
    cal_content.insert(1, "PRODID:NSO_CAL")

    # Cause whoever at NSO wrote this can't write ical's for shit and the end date is sometimes the epoch time.
    try:
        # We don't need to inject tz info as it's already set to UTC
        event = Calendar("\n".join(cal_content)).events.pop()
    except (
        ValueError
    ):  # Error occured during parsing the Calendar, as the event most likely has a start date after the end date.
        # Fall back to parsing the raw content.
        if record.text_date is None or record.text_time is None:
            print(f"Entry with url {record.link} has malformed date information")
            return

        print(
            f"Entry with url {record.link} has malformed date information, attempting to parse data"
        )
        start_dt, end_dt = parse_datetime(record.text_date, record.text_time)
        cal_content = fix_time(cal_content, start_dt, end_dt)
        event = Calendar(cal_content).events.pop()

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
    raw_description = event.description
    event.description = f"Intended audience: {' '.join(record.audience)}"
    if raw_description is not None:
        parsed_description = BS(
            raw_description, "html.parser"
        ).text.strip()  # For some reason we get unformatted html in the text. Thanks NSO
        event.description += f"\n\n{parsed_description}"

    event.url = record.link
    return (event, record.audience)


def collect_raw_entries() -> list[RawEvent]:
    """Collects the raw entries for processing later. Allows for processing to occur in a different cell.

    Returns:
        list[RawEvent|None]: List of raw events.
    """
    with ThreadPoolExecutor(MAX_WORKERS) as executor:
        return list(
            itertools.chain.from_iterable(
                executor.map(batched_fetch_raw_event, batch(event_links, 5))
            )
        )


# %%
# DEBUG
# call = get_raw_event(("https://nso.upenn.edu/event/wellness-at-penn-session/?sd=1692763200&ed=1430&ad", {Audience.ANY}))
# print(process_event(call)[0].serialize())

# %% is_executing=true
# This takes a while, don't worry if it's taking a long time.
raw_entries = collect_raw_entries()

# %%
calendar = [processed for record in raw_entries if (processed := process_event(record))]


# %% is_executing=true
def __reduction_function(cal: Calendar, event: tuple[Event, Any]):
    cal.events.add(event[0])
    return cal


def reduce_cal(cal_list: list[Entry]) -> Calendar:
    # This order matters for some reason, normally could have Calendar() as the initial parameter in the fold.
    calendar = Calendar()
    calendar.method = "REQUEST" # type: ignore
    calendar = functools.reduce(__reduction_function, iter(cal_list), calendar)
    return calendar


def create_cal(cal_list: list[Entry], predicates: set[Audience]) -> Calendar:
    events = [entry for entry in cal_list if predicates.intersection(entry[1])]
    return reduce_cal(events)


# %%
# Calendar with all events
general_calendar = reduce_cal(calendar)
with open("./output_calendars/general_calendar.ics", "w") as file:
    file.writelines(general_calendar.serialize_iter())

# %%
# Calendar for exchange students only
exchange_calendar = create_cal(calendar, {Audience.EXCHANGE_IGSP, Audience.ANY})
with open("./output_calendars/exchange_igsp_events.ics", "w") as file:
    file.writelines(exchange_calendar.serialize_iter())

# %%
transfer_calendar = create_cal(calendar, {Audience.TRANSFER, Audience.ANY})
with open("./output_calendars/transfer_events.ics", "w") as file:
    file.writelines(transfer_calendar.serialize_iter())

# %% is_executing=true magic_args="false" language="script"
# # Scratch space to figure out how the hell they broke the date time for some events so badly
#
# import datetime
# iterator = enumerate(cal_content.splitlines())
# start_index, start_time = next(x for x in iterator if x[1].startswith("DTSTART:"))
# end_index, broken_time = next(x for x in iterator if x[1].startswith("DTEND:"))
#
# print(start_time)
# dt_start_time = datetime.datetime.fromisoformat(start_time.split(":", 1)[1])
# print(broken_time)
# time = browser.find_element(By.XPATH, "//*[@id='single-events-top']/div[1]/p[2]").text
#
# split = time.splitlines()
# parsed_start = datetime.datetime.strptime(
#     split[1].rstrip().removesuffix("-").strip(), "%I:%M %p"
# ).time()
# parsed_end = datetime.datetime.strptime(split[-1].strip(), "%I:%M %p").time()
#
# parsed_start, parsed_end

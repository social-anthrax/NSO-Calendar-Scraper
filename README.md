# NSO Calendar scraper

A selenium based scraper for the [University of Pennsylvania NSO calendar](https://nso.upenn.edu/events/events-calendar/).
The calendar normally doesn't provide any way of downloading all the applicable events, so this script was created to do just that.
The generated calendars can be imported into Google Calendar, Outlook, or any other calendar software that supports the iCal format, and can be found in the releases section of this repository here: <https://github.com/social-anthrax/NSO-Calendar-Scraper/releases/tag/latest>

The calendars are dynamically updated at 1 am every day via github actions so should stay up to date. If you'd like to subscribe to the calendars (I don't personally recommend it as you won't be able to delete items, but at least it will stay up to date), copy the links below into your calendar software of choice.

- Transfer students: <https://github.com/social-anthrax/NSO-Calendar-Scraper/releases/download/latest/transfer_events.ics>
- Exchange and IGSP students: <https://github.com/social-anthrax/NSO-Calendar-Scraper/releases/download/latest/exchange_igsp_events.ics>
- First year students:
- Second year students:
- All events: <https://github.com/social-anthrax/NSO-Calendar-Scraper/releases/download/latest/general_calendar.ics>

## Calendar Entries

The scraper fixes the following issues with the standard NSO calendar entries:

- Adds the location field (Normally parsable by ICalendar, not tested on other platforms).
- Correctly displays the description (normally the description is unrendered HTML and borders on unreadable).
- Adds a link to the original event (in case you want to see the original description).
- Corrects the datetime when NSO manages to set it to the UNIX epoch, or when the end time is after the start time.
- Adds the mandatory flag to the event name.

**WARNING: IF NSO DID NOT MARK THE EVENT AUDIENCE CORRECTLY YOU WILL NOT SEE THE EVENTS, FOR EXAMPLE THE ACTIVITIES FAIR IN 2023 WAS MARKED FOR SECOND YEARS ONLY**

## Usage

The project uses [poetry for dependency management](https://python-poetry.org/) so make sure you have it installed.
Once installed use `poetry install` to install the dependencies. Tested with python 3.11.

If you wish to develop/modify the code make sure to install the development dependencies too.
`poetry install --with='dev'`
The script and notebook are kept in sync via [jupytext](https://jupytext.readthedocs.io/en/latest/), which is set up to run as a part of the pre-commit hook.
Make sure to install the precommit hooks with `poetry run pre-commit install`. This will ensure that the notebook and script are kept in sync, as well as remove the notebook output.

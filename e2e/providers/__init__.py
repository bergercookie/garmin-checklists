"""What an end-to-end run needs to know about one upstream service.

The runner in full_stack.py is identical for every provider: start the thing,
seed it, connect the bridge to it, sync a watch, tick something, and prove
nothing was written back. Only the "start it and seed it" part differs, so that
is all a fixture supplies.

Adding a provider to the end-to-end layer means one module here and one line in
full_stack.py's CHOICES.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Seeded:
    """The fixture data a run asserts against, once the service is populated."""

    #: What the phone posts to PUT /providers/<id>/config.
    config: dict[str, str]
    #: The source to import, and what it should look like on the watch.
    source_id: str
    source_name: str
    items: list[str]
    #: A second source that exists but is not imported, so the run can prove
    #: that picking one list does not drag the rest along.
    other_source_name: str
    #: Names the picker must offer. Empty means "no extra expectations".
    also_offered: list[str] = field(default_factory=list)
    #: Names the picker must NOT offer, with a reason for the failure message.
    not_offered: dict[str, str] = field(default_factory=dict)
    #: Every importable source, for the screenshot run, which wants more than
    #: one row in the watch's index.
    all_source_ids: list[str] = field(default_factory=list)


class Fixture(Protocol):
    """One upstream service, started in Docker and seeded over its own API."""

    #: The bridge's provider id, e.g. "vikunja". Also used in URLs and ids.
    provider_id: str
    label: str
    container: str

    def start(self, workspace: Path) -> str:
        """Run the container and wait for it. Returns a version for the log."""

    def seed(self) -> Seeded:
        """Create the credentials and the content the run asserts against."""

    def add_item(self, source_id: str, label: str) -> None:
        """Add one item upstream, so a re-sync can be seen to pick it up."""

    def nothing_was_ticked(self, source_id: str) -> tuple[bool, str]:
        """Whether the upstream copy is still untouched, and what was found."""

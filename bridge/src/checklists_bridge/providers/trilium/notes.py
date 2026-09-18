"""Turning the text of a Trilium note into checklist items.

Trilium notes are prose, not task lists, so an item is a line that carries a
checkbox. There are two ways to get one, and both count.

**Typed by hand**, which works in any note including plain-text ones::

    [] Mask and snorkel
    [ ] Fins
    [x] Dive computer      <- already done, never imported

**The editor's checkbox button**, which is what most people reach for. It
produces no bracket at all, just markup::

    <ul class="todo-list">
      <li><label class="todo-list__label">
        <input type="checkbox" disabled="disabled">
        <span class="todo-list__label__description">Fins</span>
      </label></li>
    </ul>

Those are rewritten into the typed form before anything else happens -- a bare
checkbox becomes ``[]`` and a ticked one ``[x]`` -- so there is one set of rules
below rather than two parsers that have to agree.

Ticked items are dropped for the same reason Vikunja's finished tasks are: the
bridge serves templates, and the watch always starts from a clean slate. So
ticking something in Trilium takes it out of the template, which is usually what
somebody means by ticking it there.

Kept apart from the HTTP client because it is the part with all the edge cases
and none of the I/O -- every rule below is a test in test_trilium_notes.py.
"""

from __future__ import annotations

import html
import re

#: Tags whose *content* is not prose. Removed wholesale rather than unwrapped.
_DROPPED_ELEMENTS = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)

#: Tags that end a visual line. Trilium's editor wraps every paragraph in <p>
#: and every bullet in <li>; without this the whole note collapses onto one
#: line and not a single item matches.
_LINE_BREAKS = re.compile(
    r"</?(br|p|div|li|tr|h[1-6]|blockquote|section|article)\b[^>]*>",
    re.IGNORECASE,
)

_ANY_TAG = re.compile(r"<[^>]+>")

#: The editor's own checkbox. Trilium (CKEditor) writes a todo-list as an
#: <input type="checkbox"> followed by the label text, with `checked` present
#: only when it is done -- there is no bracket anywhere in the markup.
_CHECKBOX_INPUT = re.compile(r"""<input\b[^>]*\btype=["']?checkbox["']?[^>]*>""", re.IGNORECASE)

#: Distinguishes `<input ... checked>` from `<input ... disabled>`; both appear.
_CHECKED = re.compile(r"\bchecked\b", re.IGNORECASE)

#: A leading bullet, for `- [] x` and for the `<li>` markers some editors emit
#: as literal text.
# Bullet characters, deliberately: an editor may emit any of them, and the
# ambiguity ruff warns about is the whole point of matching them all.
_LIST_MARKER = re.compile(r"^[-*•–]\s+")  # noqa: RUF001

#: The checkbox itself: `[]`, `[ ]`, `[x]`, `[ X ]`. Group 1 is the tick.
_CHECKBOX = re.compile(r"^\[\s*([xX]?)\s*\]\s*(\S.*)$")


def _as_typed_checkbox(match: re.Match[str]) -> str:
    """Rewrite one editor checkbox as the bracket form the rules below expect."""
    return "[x] " if _CHECKED.search(match.group(0)) else "[] "


def plain_lines(content: str) -> list[str]:
    """Flatten note content -- HTML or plain text -- into visual lines."""
    text = _DROPPED_ELEMENTS.sub(" ", content)
    # Before the tags are stripped, or the checkbox would vanish with them and
    # a note written with the editor's own button would import as empty.
    text = _CHECKBOX_INPUT.sub(_as_typed_checkbox, text)
    text = _LINE_BREAKS.sub("\n", text)
    text = _ANY_TAG.sub("", text)
    text = html.unescape(text)
    # A non-breaking space is whitespace to a reader and to nobody else; the
    # editor emits them freely, and `[]\xa0Fins` would otherwise not match.
    text = text.replace("\xa0", " ")
    return [line.strip() for line in text.split("\n")]


def checklist_items(content: str) -> list[str]:
    """Every unticked ``[]`` line in the note, in the order they appear.

    Lines that are not checkboxes -- headings, notes to self, blank lines -- are
    ignored rather than imported, so a note can hold a checklist and prose at
    once.
    """
    items = []
    for line in plain_lines(content):
        label = _item_label(line)
        if label is not None:
            items.append(label)
    return items


def _item_label(line: str) -> str | None:
    """The item on this line, or None if it is not an unticked checkbox."""
    match = _CHECKBOX.match(_LIST_MARKER.sub("", line.strip()))
    if match is None or match.group(1):
        return None
    return match.group(2).strip()

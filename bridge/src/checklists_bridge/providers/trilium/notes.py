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

**Links to other checklists.** An item may contain a link to another note --
the editor's *Insert → Link* or a typed ``[[`` reference, or any ordinary
``<a href="#root/…/noteId">``. The note id is read from the link, and the
bridge unrolls the item into that checklist if the note is one (see
flatten.py). So ``[] <a href="#root/x/abc123">LKP night routine</a>`` brings in
the *LKP night routine* checklist under that item. The link text stays as the
item's own text; whether it resolves is decided later, not here.

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

#: An anchor and its attributes and content. Handled before the tags are
#: stripped, because stripping them would throw the destination away.
_ANCHOR = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.IGNORECASE | re.DOTALL)
_HREF = re.compile(r"""\bhref\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.IGNORECASE)

#: Private-use characters that carry a link target through the tag stripping,
#: attached to the end of the link's text. They cannot occur in a note.
_TARGET_OPEN, _TARGET_CLOSE = "\ue000", "\ue001"
_TARGET = re.compile(f"{_TARGET_OPEN}([^{_TARGET_CLOSE}]*){_TARGET_CLOSE}")

#: What a Trilium note id looks like. Generous on purpose: custom ids exist.
_NOTE_ID = re.compile(r"[A-Za-z0-9_]{1,64}")

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


def note_id_from_href(href: str) -> str | None:
    """The note a Trilium link points at, or None if it is not a note link.

    Trilium links are a fragment holding the path through the note tree, the
    note's own id last: ``#root/abc123/def456`` points at ``def456``. They turn
    up bare, as ``/#root/…``, and with the instance's full address in front, so
    only the fragment is read. A ``?viewMode=…`` after it is ignored.
    """
    _, hash_mark, fragment = html.unescape(href).strip().partition("#")
    if not hash_mark:
        return None
    segments = [part for part in fragment.split("?", 1)[0].split("/") if part]
    if not segments or (len(segments) > 1 and segments[0] != "root"):
        return None
    return segments[-1] if _NOTE_ID.fullmatch(segments[-1]) else None


def _tag_link(match: re.Match[str]) -> str:
    """Keep an anchor's text, with the note it points at tucked behind it."""
    href = _HREF.search(match.group(1))
    target = note_id_from_href(href.group(1) or href.group(2) or "") if href else None
    if target is None:
        return match.group(2)
    return f"{match.group(2)}{_TARGET_OPEN}{target}{_TARGET_CLOSE}"


def plain_lines(content: str, *, keep_links: bool = False) -> list[str]:
    """Flatten note content -- HTML or plain text -- into visual lines.

    With ``keep_links`` each link's target note id follows the link's text,
    wrapped in private-use characters; see :func:`checklist_entries`.
    """
    text = _DROPPED_ELEMENTS.sub(" ", content)
    text = _ANCHOR.sub(_tag_link if keep_links else r"\2", text)
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
    return [label for label, _ in checklist_entries(content)]


def checklist_entries(content: str) -> list[tuple[str, tuple[str, ...]]]:
    """:func:`checklist_items`, each with the notes its line links to.

    The targets are note ids in the order the links appear, empty for an item
    with no link. A link on a line that is not a checkbox is not an item's link
    and is ignored with the rest of the prose.
    """
    entries = []
    for line in plain_lines(content, keep_links=True):
        targets = tuple(_TARGET.findall(line))
        label = _item_label(_TARGET.sub("", line))
        if label is not None:
            entries.append((label, targets))
    return entries


def _item_label(line: str) -> str | None:
    """The item on this line, or None if it is not an unticked checkbox."""
    match = _CHECKBOX.match(_LIST_MARKER.sub("", line.strip()))
    if match is None or match.group(1):
        return None
    return match.group(2).strip()

"""The `[]` syntax: what counts as an item and what does not."""

from __future__ import annotations

import pytest

from checklists_bridge.providers.trilium.notes import checklist_items, plain_lines


def test_a_paragraph_per_item_is_what_the_editor_actually_writes() -> None:
    # Trilium's editor wraps every line in <p>. If those were not turned into
    # line breaks the whole note would collapse onto one line and nothing would
    # match at all.
    content = "<p>[] Mask</p><p>[] Fins</p><p>[] Dive computer</p>"
    assert checklist_items(content) == ["Mask", "Fins", "Dive computer"]


def test_bullet_lists_work_too() -> None:
    content = "<ul><li>[] Mask</li><li>[] Fins</li></ul>"
    assert checklist_items(content) == ["Mask", "Fins"]


def test_line_breaks_inside_one_paragraph_separate_items() -> None:
    assert checklist_items("<p>[] Mask<br>[] Fins<br />[] Reel</p>") == [
        "Mask",
        "Fins",
        "Reel",
    ]


def test_a_plain_text_note_needs_no_html_at_all() -> None:
    # A Trilium "code" note with mime text/plain comes back unwrapped.
    assert checklist_items("[] Mask\n[] Fins\n") == ["Mask", "Fins"]


@pytest.mark.parametrize("marker", ["[]", "[ ]", "[  ]"])
def test_an_empty_box_is_an_item_however_it_is_spaced(marker: str) -> None:
    assert checklist_items(f"<p>{marker} Fins</p>") == ["Fins"]


@pytest.mark.parametrize("marker", ["[x]", "[X]", "[ x ]"])
def test_a_ticked_box_is_dropped_entirely(marker: str) -> None:
    # Same rule as Vikunja's finished tasks: the watch only ever gets a template
    # to start from, so ticking a line in Trilium removes it.
    assert checklist_items(f"<p>[] Mask</p><p>{marker} Fins</p>") == ["Mask"]


def test_prose_around_the_checklist_is_ignored() -> None:
    content = (
        "<h2>Dive kit</h2>"
        "<p>Packed the night before.</p>"
        "<p>[] Mask</p>"
        "<p>Remember the spare mask if diving deep.</p>"
        "<p>[] Fins</p>"
    )
    assert checklist_items(content) == ["Mask", "Fins"]


def test_a_note_with_no_checkboxes_yields_nothing() -> None:
    assert checklist_items("<p>Just some thoughts.</p><p>Nothing to pack.</p>") == []


def test_empty_content_yields_nothing() -> None:
    assert checklist_items("") == []


def test_a_box_with_no_label_is_not_an_item() -> None:
    assert checklist_items("<p>[]</p><p>[] </p><p>[] Fins</p>") == ["Fins"]


def test_a_leading_bullet_before_the_box_is_tolerated() -> None:
    assert checklist_items("<p>- [] Mask</p><p>* [] Fins</p><p>• [] Reel</p>") == [
        "Mask",
        "Fins",
        "Reel",
    ]


def test_a_box_without_a_space_before_the_label_still_counts() -> None:
    assert checklist_items("<p>[]Fins</p>") == ["Fins"]


def test_a_box_that_is_not_at_the_start_of_the_line_is_not_an_item() -> None:
    # Otherwise a sentence mentioning the syntax would import itself.
    assert checklist_items("<p>Write [] before an item.</p>") == []


def test_entities_are_decoded_so_the_watch_shows_what_trilium_shows() -> None:
    assert checklist_items("<p>[] Mask &amp; snorkel</p>") == ["Mask & snorkel"]


def test_a_non_breaking_space_after_the_box_still_matches() -> None:
    # The editor emits these freely, and they are whitespace to a reader.
    assert checklist_items("<p>[]&nbsp;Fins</p>") == ["Fins"]


def test_inline_formatting_inside_a_label_is_stripped() -> None:
    assert checklist_items("<p>[] <strong>Dive</strong> computer</p>") == ["Dive computer"]


def test_a_formatted_box_still_counts() -> None:
    # Bolding the whole line puts a tag before the bracket.
    assert checklist_items("<p><strong>[] Fins</strong></p>") == ["Fins"]


def test_script_and_style_content_is_not_mistaken_for_prose() -> None:
    content = "<style>p { content: '[] not an item'; }</style><p>[] Fins</p>"
    assert checklist_items(content) == ["Fins"]


def test_nested_lists_keep_document_order() -> None:
    content = "<ul><li>[] Mask</li><ul><li>[] Spare strap</li></ul><li>[] Fins</li></ul>"
    assert checklist_items(content) == ["Mask", "Spare strap", "Fins"]


def test_plain_lines_flattens_without_deciding_what_is_an_item() -> None:
    # The split is worth testing on its own: every item rule depends on it.
    # Adjacent tags leave blank lines behind, which is fine -- a blank line is
    # not a checkbox, so checklist_items skips it.
    assert plain_lines("<p>one</p><p>two</p>") == ["", "one", "", "two", ""]


#: Verbatim from a note created with Trilium's own checkbox button. There is no
#: bracket anywhere in it, which is why the typed-`[]` rules alone found nothing.
EDITOR_TODO_LIST = """<ul class="todo-list">
<li data-list-item-id="e587e2ea8a87d2e50ea65e6d6bd6514f8"><label class="todo-list__label"><input type="checkbox" disabled="disabled"><span
class="todo-list__label__description">a</span></label></li>
<li data-list-item-id="ead2e8e2de5b7839c09d38ae7f44b584b"><label class="todo-list__label"><input type="checkbox" disabled="disabled"><span
class="todo-list__label__description">b</span></label></li>
<li data-list-item-id="eaf27be93280d2b7761f46ae22e209d90"><label class="todo-list__label"><input type="checkbox" disabled="disabled"><span
class="todo-list__label__description">c</span></label></li>
</ul>"""


def test_the_editors_own_checkbox_list_is_a_checklist() -> None:
    assert checklist_items(EDITOR_TODO_LIST) == ["a", "b", "c"]


def test_a_ticked_editor_checkbox_is_dropped_like_a_ticked_line() -> None:
    content = (
        '<ul class="todo-list">'
        '<li><label class="todo-list__label"><input type="checkbox" disabled="disabled">'
        '<span class="todo-list__label__description">Mask</span></label></li>'
        '<li><label class="todo-list__label">'
        '<input type="checkbox" checked="checked" disabled="disabled">'
        '<span class="todo-list__label__description">Fins</span></label></li>'
        "</ul>"
    )
    assert checklist_items(content) == ["Mask"]


def test_a_bare_checked_attribute_counts_as_ticked() -> None:
    # The attribute is sometimes written without a value.
    content = (
        '<ul class="todo-list"><li><label><input type="checkbox" checked>'
        '<span class="todo-list__label__description">Done</span></label></li></ul>'
    )
    assert checklist_items(content) == []


def test_typed_and_editor_checkboxes_can_share_one_note() -> None:
    content = (
        "<p>[] Typed one</p>"
        '<ul class="todo-list"><li><label><input type="checkbox">'
        '<span class="todo-list__label__description">Clicked one</span></label></li></ul>'
        "<p>[x] Typed and done</p>"
    )
    assert checklist_items(content) == ["Typed one", "Clicked one"]


def test_a_checkbox_input_outside_a_list_still_counts() -> None:
    # Nothing in the rules depends on the surrounding <ul class="todo-list">,
    # which means a future editor change to that wrapper cannot silently empty
    # everybody's checklists.
    assert checklist_items('<p><input type="checkbox"> Loose item</p>') == ["Loose item"]


def test_a_non_checkbox_input_is_not_an_item() -> None:
    assert checklist_items('<p><input type="text" value="not a checkbox"> Typed</p>') == []

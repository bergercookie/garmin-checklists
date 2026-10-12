from __future__ import annotations

import threading
from pathlib import Path

import pytest

import fakes
from checklists_bridge.models import DomainError, SourceRef
from checklists_bridge.providers.base import ProviderAuthError, ProviderError
from checklists_bridge.providers.registry import ProviderRegistry
from checklists_bridge.service import ChecklistService, NotFoundError
from checklists_bridge.storage import Database
from conftest import configure_fake


def test_unknown_provider_is_rejected(service: ChecklistService) -> None:
    with pytest.raises(ProviderError):
        service.list_sources("nope")


def test_configure_provider_validates_credentials_before_saving(service: ChecklistService) -> None:
    fakes.FAIL["auth"] = True
    with pytest.raises(ProviderAuthError):
        service.configure_provider("fake", {"token": "t"})
    assert service._database.read().providers.get("fake") is None


def test_configure_provider_returns_importable_sources(service: ChecklistService) -> None:
    sources = service.configure_provider("fake", {"token": "t"})
    assert {source.name for source in sources} == {"Dive kit", "Travel"}


def test_missing_required_config_is_rejected(service: ChecklistService) -> None:
    with pytest.raises(ProviderError, match="missing required"):
        service.configure_provider("fake", {})


def test_secrets_are_redacted_but_kept_on_resave(service: ChecklistService) -> None:
    service.configure_provider("fake", {"token": "s3cret"})
    status = next(item for item in service.provider_statuses() if item.spec.id == "fake")
    assert status.config["token"] == "********"

    service.configure_provider("fake", {"token": "********"})
    assert service._database.read().providers["fake"].config["token"] == "s3cret"


def test_refresh_snapshots_the_selected_sources_only(service: ChecklistService) -> None:
    service.configure_provider("fake", {"token": "t"})
    service.set_selection("fake", ["a"])
    report = service.refresh()
    assert report.ok
    assert [item.id for item in report.checklists] == ["fake:a"]
    assert report.checklists[0].items == ("Mask", "Fins")


def test_refresh_keeps_the_previous_copy_when_a_provider_breaks(service: ChecklistService) -> None:
    configure_fake(service)
    fakes.FAIL["auth"] = True

    report = service.refresh()

    assert not report.ok
    assert report.errors
    assert {item.id for item in report.checklists} == {"fake:a", "fake:b"}


def test_deselecting_a_source_drops_it_from_the_snapshot(service: ChecklistService) -> None:
    configure_fake(service)
    service.set_selection("fake", ["a"])
    assert [item.id for item in service.snapshot()[0]] == ["fake:a"]


def test_forgetting_a_provider_clears_its_checklists(service: ChecklistService) -> None:
    configure_fake(service)
    service.forget_provider("fake")
    assert service.snapshot()[0] == []


def test_snapshot_checklist_lookup(service: ChecklistService) -> None:
    configure_fake(service)
    assert service.snapshot_checklist("fake:b").name == "Travel"
    with pytest.raises(NotFoundError):
        service.snapshot_checklist("fake:zzz")


def test_local_checklists_reach_the_watch_without_extra_steps(service: ChecklistService) -> None:
    created = service.create_local_checklist("Pre-dive")
    service.set_local_items(created.id, ["Air check", "Weights"])
    report = service.refresh()
    assert [item.name for item in report.checklists] == ["Pre-dive"]
    assert report.checklists[0].items == ("Air check", "Weights")


def test_deleting_a_local_checklist_removes_it_from_the_next_sync(
    service: ChecklistService,
) -> None:
    created = service.create_local_checklist("Pre-dive")
    service.refresh()
    service.delete_local_checklist(created.id)
    assert service.refresh().checklists == ()


def test_local_checklist_names_are_validated(service: ChecklistService) -> None:
    with pytest.raises(DomainError):
        service.create_local_checklist(" ")


def test_rotating_the_device_token_changes_it(service: ChecklistService) -> None:
    before = service.device_token
    assert service.rotate_device_token() != before
    assert service.device_token != before


def test_refresh_keeps_checklists_when_the_provider_cannot_be_built(
    service: ChecklistService,
) -> None:
    configure_fake(service)
    with service._database.update() as state:
        state.providers["fake"].config = {}  # credentials removed, selection kept

    report = service.refresh()

    assert not report.ok
    assert "missing required" in report.errors[0]
    assert {item.id for item in report.checklists} == {"fake:a", "fake:b"}


def test_a_provider_with_nothing_selected_is_skipped(service: ChecklistService) -> None:
    service.configure_provider("fake", {"token": "t"})
    assert service.refresh().checklists == ()


def test_registering_the_same_provider_twice_is_refused(registry: ProviderRegistry) -> None:
    with pytest.raises(ValueError, match="already registered"):
        registry.register(fakes.SPEC)


def test_two_phones_adding_checklists_at_once_lose_none(tmp_path: Path) -> None:
    # Read-modify-write across two separate lock acquisitions used to drop about
    # half of these, and leave the selection pointing at checklists that no
    # longer existed -- which then failed every refresh, for good.
    service = ChecklistService(Database(tmp_path / "bridge.json"))
    writers, each = 4, 25
    start = threading.Barrier(writers)

    def add(worker: int) -> None:
        start.wait()
        for index in range(each):
            service.create_local_checklist(f"list-{worker}-{index}")

    threads = [threading.Thread(target=add, args=(worker,)) for worker in range(writers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    state = service._database.read()
    assert len(state.local_checklists) == writers * each
    stored_ids = {item.id for item in state.local_checklists}
    assert set(state.provider("local").selection) <= stored_ids


def test_concurrent_renames_of_one_checklist_do_not_lose_the_others(tmp_path: Path) -> None:
    service = ChecklistService(Database(tmp_path / "bridge.json"))
    made = [service.create_local_checklist(f"list-{index}") for index in range(10)]
    start = threading.Barrier(len(made))

    def rename(ref: SourceRef) -> None:
        start.wait()
        service.rename_local_checklist(ref.id, f"{ref.name} renamed")

    threads = [threading.Thread(target=rename, args=(ref,)) for ref in made]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    names = {item.name for item in service._database.read().local_checklists}
    assert names == {f"list-{index} renamed" for index in range(10)}


def test_a_failed_refresh_does_not_claim_the_snapshot_is_fresh(service: ChecklistService) -> None:
    configure_fake(service)
    first = service.refresh()
    assert first.ok
    fresh_at = service.sync_health().synced_at

    fakes.FAIL["auth"] = True
    second = service.refresh()

    assert not second.ok
    health = service.sync_health()
    # The watch is still being served the old copy, so "last synced" has to keep
    # pointing at when that copy was actually fetched.
    assert health.synced_at == fresh_at
    assert health.attempted_at > 0
    assert health.errors and "fake provider says no" in health.errors[0]


def test_a_recovered_provider_clears_the_reported_errors(service: ChecklistService) -> None:
    configure_fake(service)
    fakes.FAIL["auth"] = True
    service.refresh()
    assert service.sync_health().errors

    fakes.FAIL["auth"] = False

    service.refresh()
    assert service.sync_health().ok
    assert service.sync_health().synced_at == service.sync_health().attempted_at


def test_providers_are_closed_after_every_refresh(
    service: ChecklistService, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed: list[str] = []
    monkeypatch.setattr(
        fakes.FakeProvider, "close", lambda self: closed.append(self.__class__.id), raising=False
    )
    configure_fake(service)
    service.refresh()
    assert closed, "the provider built for the refresh was never closed"


def test_refresh_unrolls_links_between_the_selected_checklists(service: ChecklistService) -> None:
    service.configure_provider("fake", {"token": "t"})
    service.set_selection("fake", ["a", "b"])
    fakes.LINKS["a"] = {0: ("b",)}
    report = service.refresh()

    unrolled = service.snapshot_checklist("fake:a")
    assert unrolled.items == ("Mask", "Passport", "Fins")
    assert unrolled.depths == (0, 1, 0)
    assert unrolled.groups == (0,)
    assert report.checklists[0] == unrolled
    # The linked list is still a checklist in its own right.
    assert service.snapshot_checklist("fake:b").items == ("Passport",)


def test_a_link_to_a_checklist_that_is_not_selected_is_still_unrolled(
    service: ChecklistService,
) -> None:
    service.configure_provider("fake", {"token": "t"})
    service.set_selection("fake", ["a"])
    fakes.LINKS["a"] = {0: ("b",)}
    service.refresh()

    assert service.snapshot_checklist("fake:a").items == ("Mask", "Passport", "Fins")
    # Only the linking list is served: the one linked to was never selected.
    assert [item.id for item in service.snapshot()[0]] == ["fake:a"]


def test_a_link_to_something_that_is_not_a_checklist_is_left_as_text(
    service: ChecklistService,
) -> None:
    service.configure_provider("fake", {"token": "t"})
    service.set_selection("fake", ["a"])
    fakes.LINKS["a"] = {0: ("not-a-checklist",)}
    report = service.refresh()
    assert report.ok
    assert service.snapshot_checklist("fake:a").items == ("Mask", "Fins")


def test_a_link_to_a_note_that_was_deleted_is_left_as_text_without_an_error(
    service: ChecklistService,
) -> None:
    service.configure_provider("fake", {"token": "t"})
    service.set_selection("fake", ["a"])
    fakes.LINKS["a"] = {0: ("gone",)}
    fakes.GONE.add("gone")
    assert service.refresh().ok
    assert service.snapshot_checklist("fake:a").items == ("Mask", "Fins")


def test_a_linked_checklist_can_link_onwards_to_another_unselected_one(
    service: ChecklistService,
) -> None:
    fakes.CONTENT["c"] = ["Charger"]
    fakes.NAMES["c"] = "Gadgets"
    service.configure_provider("fake", {"token": "t"})
    service.set_selection("fake", ["a"])
    fakes.LINKS["a"] = {0: ("b",)}
    fakes.LINKS["b"] = {0: ("c",)}
    service.refresh()
    flat = service.snapshot_checklist("fake:a")
    assert flat.items == ("Mask", "Passport", "Charger", "Fins")
    assert flat.depths == (0, 1, 2, 0)


def test_a_link_cycle_through_unselected_lists_terminates(service: ChecklistService) -> None:
    service.configure_provider("fake", {"token": "t"})
    service.set_selection("fake", ["a"])
    fakes.LINKS["a"] = {0: ("b",)}
    fakes.LINKS["b"] = {0: ("a",)}
    service.refresh()
    assert service.snapshot_checklist("fake:a").items == ("Mask", "Passport", "Fins")


def test_only_so_many_unselected_lists_are_fetched_for_links(
    service: ChecklistService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("checklists_bridge.service.MAX_LINKED", 1)
    fakes.CONTENT["c"] = ["Charger"]
    fakes.NAMES["c"] = "Gadgets"
    service.configure_provider("fake", {"token": "t"})
    service.set_selection("fake", ["a"])
    fakes.LINKS["a"] = {0: ("b",), 1: ("c",)}
    service.refresh()
    # The first lookup is used, the second is over the budget and stays text.
    assert service.snapshot_checklist("fake:a").items == ("Mask", "Passport", "Fins")


def test_a_provider_that_fails_on_a_linked_note_is_reported_not_hidden(
    service: ChecklistService,
) -> None:
    service.configure_provider("fake", {"token": "t"})
    service.set_selection("fake", ["a"])
    fakes.LINKS["a"] = {0: ("b",)}
    fakes.FAIL["linked"] = True
    report = service.refresh()
    assert not report.ok
    assert "fake/b" in report.errors[0]
    assert service.snapshot_checklist("fake:a").items == ("Mask", "Fins")


def test_a_failed_fetch_of_the_linked_list_falls_back_to_last_refreshs_copy(
    service: ChecklistService,
) -> None:
    service.configure_provider("fake", {"token": "t"})
    service.set_selection("fake", ["a", "b"])
    service.refresh()

    fakes.LINKS["a"] = {0: ("b",)}
    del fakes.CONTENT["b"]  # b can no longer be fetched
    report = service.refresh()

    assert not report.ok
    assert service.snapshot_checklist("fake:a").items == ("Mask", "Passport", "Fins")


def test_unrolled_lists_survive_a_restart(service: ChecklistService, tmp_path: Path) -> None:
    service.configure_provider("fake", {"token": "t"})
    service.set_selection("fake", ["a", "b"])
    fakes.LINKS["a"] = {0: ("b",)}
    service.refresh()

    reopened = ChecklistService(Database(tmp_path / "bridge.json"), service._registry)
    assert reopened.snapshot_checklist("fake:a").depths == (0, 1, 0)

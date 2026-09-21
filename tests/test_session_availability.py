import csv
import json
from dataclasses import replace

from evil_sorter.config import ROOT, load_settings
from evil_sorter.data import EvilData
from evil_sorter.store import DecisionStore


def test_missing_failed_and_zero_cell_sessions_are_distinct(tmp_path):
    catalog = tmp_path / "catalog.csv"
    with catalog.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["group", "mouse_id", "session_id", "variant",
            "run_id", "analysis_id", "frame_count", "n_native_accepted", "n_soma_valid", "duration_s"])
        writer.writeheader()
        for session, cells in [(2, 3), (3, 2), (4, 0)]:
            writer.writerow(dict(group="AM", mouse_id="mouse", session_id=session,
                variant="standard", run_id=f"run{session}", analysis_id="analysis",
                frame_count=100, n_native_accepted=cells, n_soma_valid=0, duration_s=10))
        writer.writerow(dict(group="AM", mouse_id="mouse", session_id=8,
            variant="alternate", run_id="run8alternate", analysis_id="analysis",
            frame_count=100, n_native_accepted=2, n_soma_valid=0, duration_s=10))
    reconciliation = tmp_path / "reconciliation.csv"
    reconciliation.write_text("condition,mouse_id,session_id,variant,status,exclusion_reason\n"
                              "am,mouse,5,standard,excluded,corrupt TIFF\n")
    exclusions = tmp_path / "exclusions.json"
    exclusions.write_text(json.dumps({"exclusions": []}))
    settings = replace(load_settings(ROOT / "config.example.json"), catalog=catalog, reconciliation=reconciliation,
        exclusion_registry=exclusions, show_unavailable_sessions=(1, 2, 3, 4, 5, 6, 8), review_sessions=(3, 4, 5, 6, 8),
        decision_database=tmp_path / "decisions.sqlite")
    store = DecisionStore(settings.decision_database)
    store.put("analysis", "run2", 0, "keep", "test")
    data = EvilData(settings, store)
    sessions = {r["session"]: r for r in data.catalog()["groups"]["AM"]["mouse"]}
    assert set(sessions) == {3, 4, 5, 6, 8}
    assert sessions[3]["available"]
    assert sessions[4]["status"] == "no_reviewable_cells"
    assert not sessions[4]["available"]
    assert sessions[5]["reason"] == "corrupt TIFF"
    assert sessions[6]["status"] == "not_in_catalog"
    assert not sessions[6]["available"]
    assert sessions[8]["variant"] == "alternate"
    assert sessions[8]["available"]
    assert "run2" not in data.by_run
    assert store.get_run("run2")[0]["decision"] == "keep"
    data.settings = replace(settings, downstream_selection=tmp_path / "selection.json")
    exported = data.export_selection()
    assert exported["review_sessions"] == [3, 4, 5, 6, 8]
    assert all(x["session_id"] >= 3 for x in exported["unreviewed_runs"])
    assert "run2" not in exported["runs"]


def test_unconfigured_scope_includes_all_sessions_and_groups_new_sessions(tmp_path):
    settings = load_settings(ROOT / "config.example.json")
    assert settings.review_sessions is None
    assert settings.modalities == ()
    data = EvilData.__new__(EvilData)
    data.settings = replace(settings, modalities=({"id": "training", "label": "Training", "sessions": [1, 2]},))
    data.rows = [{"session_id": 1}, {"session_id": 7}]
    data.unavailable_rows = []
    assert data.session_modalities()[-1]["sessions"] == [7]

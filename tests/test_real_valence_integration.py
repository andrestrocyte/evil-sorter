from pathlib import Path

import pytest

from evil_sorter.config import Settings
from evil_sorter.data import EvilData
from evil_sorter.selection import load_manual_keep
from evil_sorter.store import DecisionStore


CATALOG = Path("/Users/deviandr/Documents/evil_caiman/reports/valence-presentation-20260821-v2-atlas/sources/session_atlas/session_atlas_index.csv")
MOUNT = Path("/Volumes/gluthi/deviandr/evil_caiman_calcium")


@pytest.mark.skipif(not CATALOG.exists() or not MOUNT.exists(), reason="valence catalog/Tachyon mount unavailable")
def test_real_catalog_exclusion_and_atomic_downstream_export(tmp_path: Path):
    settings = Settings(
        host="127.0.0.1", port=0,
        evil_caiman_root=Path("/Users/deviandr/Documents/evil_caiman"),
        tachyon_mount=MOUNT, catalog=CATALOG,
        reconciliation=Path("/Users/deviandr/Documents/evil_caiman/reports/valence-presentation-20260821-v2-atlas/sources/session_atlas/session-reconciliation.csv"),
        exclusion_registry=Path("/Users/deviandr/Documents/evil_caiman/configs/valence_analysis_exclusions.json"),
        decision_database=tmp_path / "decisions.sqlite",
        downstream_selection=tmp_path / "selection.json", reviewer="test",
        component_gate="native_accepted", chunk_minutes=10,
        show_unavailable_sessions=(3, 4), auto_advance=True,
    )
    store = DecisionStore(settings.decision_database)
    data = EvilData(settings, store)
    assert "ALU-00471" in data.excluded
    assert all(row["mouse_id"] != "ALU-00471" for row in data.rows)
    am_3407 = data.catalog()["groups"]["AM"]["ALU-03407"]
    assert any(x["session"] == 4 and not x["available"] for x in am_3407)
    run_id = "ALU-00372-session-3-standard-Session_3-ch2-index-001"
    info = data.run_info(run_id)
    component_id = info["components"][0]["component_id"]
    store.put(info["row"]["analysis_id"], run_id, component_id, "keep", "test")
    exported = data.export_selection()
    assert settings.downstream_selection.exists()
    assert exported["runs"][run_id]["manual_keep_component_ids"] == [component_id]
    assert load_manual_keep(settings.downstream_selection, run_id, require_complete=False) == [component_id]

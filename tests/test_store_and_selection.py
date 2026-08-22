import json
from pathlib import Path

import pytest

from evil_sorter.selection import load_manual_keep
from evil_sorter.store import DecisionStore


def test_decisions_are_upserted_by_run_and_component(tmp_path: Path):
    store = DecisionStore(tmp_path / "decisions.sqlite")
    store.put("analysis", "run", 7, "keep", "reviewer")
    store.put("analysis", "run", 7, "reject", "reviewer", "motion")
    rows = store.get_run("run")
    assert list(rows) == [7]
    assert rows[7]["decision"] == "reject"
    assert rows[7]["note"] == "motion"


def test_selection_requires_complete_review(tmp_path: Path):
    path = tmp_path / "selection.json"
    path.write_text(json.dumps({"selection_gate": "evil_sorter_manual_keep", "runs": {
        "run": {"review_complete": False, "native_accepted_component_ids": [2, 3],
                "manual_keep_component_ids": [2]}}}))
    with pytest.raises(RuntimeError):
        load_manual_keep(path, "run")
    assert load_manual_keep(path, "run", require_complete=False) == [2]


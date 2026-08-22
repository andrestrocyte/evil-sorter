# Evil Sorter

<p align="center">
  <img src="static/assets/evil_sorter_logo.png" alt="Evil Sorter logo" width="520">
</p>

Calcium imaging gives us thousands of candidate signals, but not every extracted
component looks like a neuron that should carry biological interpretation.
Evil Sorter is a visual review room for that judgment. It places each candidate
back inside its field of view and shows how its fluorescence evolves through the
entire experiment and through shorter ten-minute windows.

The goal is simple: make cell inclusion a decision that a neuroscientist can see,
defend, and reproduce. Reviewers can move through the native CaImAn-accepted
population, compare `F_dff`, denoised calcium `C`, and deconvolved activity `S`,
and mark each component as keep or reject without altering the original
extraction. Those decisions become a separate, auditable layer for later PSTHs,
population analyses, decoding, and representation studies.

## What you see while reviewing

- The cell's footprint highlighted within the full field of view.
- Its complete session-long activity trace, with zoom and pan.
- Consecutive ten-minute views that reveal long silent periods, recurrent
  transients, drift, and suspiciously binary or noisy signals.
- Immediate progress and keep/reject counts drawn from the decision database.
- Group, mouse, and session selectors that preserve unavailable sessions as
  visible, documented gaps rather than silently hiding them.

The original CaImAn decision remains immutable. Evil Sorter stores the manual
decision separately using the stable identity
`analysis_id + run_id + component_id`.

## Launch

Copy `config.example.json` to the ignored local file `config.json`, then set
the paths to your `evil_caiman` catalog, mounted outputs, exclusion registry,
decision database, and downstream export.

Double-click `Evil Sorter.command`, or run:

```bash
./Evil\ Sorter.command
```

The app opens at `http://127.0.0.1:8765`.

## Reviewing cells

- Choose group, mouse and session in the left sidebar.
- Changing group or mouse immediately loads the corresponding run while preserving
  the current session number when that session exists for the new mouse.
- Requested sessions that exist in the inventory but have no closed CaImAn run
  remain visible as disabled `unavailable` entries with the audited reason.
- Use Previous/Next or the arrow keys to move between native accepted cells.
- Press **A** or click the green tick to keep a cell.
- Press **X** or click the red cross to reject a cell.
- Mouse-wheel over the FOV or traces to zoom; drag to pan; double-click to reset.
- Move the chunk slider to inspect consecutive 10-minute windows.
- Decisions save immediately and review resumes where it stopped.

## From visual judgment to analysis

Live database:

`data/evil_sorter_decisions.sqlite`

Machine-readable downstream selection, rewritten atomically after each review:

the path configured as `downstream_selection` in your local `config.json`.

The exported JSON records reviewed keep/reject component IDs, pending cells,
source provenance, and a deterministic digest. Downstream code must explicitly
request the `evil_sorter_manual_keep` population, so an exploratory judgment can
never silently replace the canonical CaImAn result.

Python consumers can use `evil_sorter.selection.load_manual_keep(...)`, which
rejects incomplete reviews by default.

## Relationship to Evil Caiman

Evil Sorter is designed as the human curation layer beside
[`evil_caiman`](https://github.com/andrestrocyte/evil_caiman). It reads the
catalog and one component at a time from mounted CaImAn outputs. It never copies
full recordings or writes into completed analyses.

Selector state is race-safe: stale requests are aborted and their responses are
ignored, so rapid mouse changes cannot overwrite the most recent selection.

## Privacy and provenance

`config.json`, SQLite decisions, and exported selections are ignored by Git.
The public repository contains no imaging data or manual decisions. Source
CaImAn results are read-only; the manual layer is stored separately.

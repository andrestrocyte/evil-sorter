# Evil Sorter

Evil Sorter is a fast, local, provenance-preserving cell-review interface for
official `evil_caiman` CaImAn outputs. It lets a reviewer inspect every native
accepted component in its FOV together with whole-session and ten-minute
windows of `F_dff`, denoised calcium `C`, and deconvolved activity `S`.

The original CaImAn decision is immutable. Evil Sorter stores a second manual
layer keyed by:

`analysis_id + run_id + component_id`

## Launch

Double-click `Evil Sorter.command`, or run:

```bash
./Evil\ Sorter.command
```

The app opens at `http://127.0.0.1:8765`.

## Review controls

- Choose group, mouse and session in the left sidebar.
- Use Previous/Next or the arrow keys to move between native accepted cells.
- Press **A** or click the green tick to keep a cell.
- Press **X** or click the red cross to reject a cell.
- Mouse-wheel over the FOV or traces to zoom; drag to pan; double-click to reset.
- Move the chunk slider to inspect consecutive 10-minute windows.
- Decisions save immediately and review resumes where it stopped.

## Persistence and downstream contract

Live database:

`data/evil_sorter_decisions.sqlite`

Machine-readable downstream selection, rewritten atomically after each review:

`/Users/deviandr/Documents/evil_caiman/configs/manual_cell_selections/evil_sorter_valence_native_v1.json`

The JSON contains reviewed keep/reject component IDs, pending native accepted
components, source paths, exclusion registry digest and a deterministic digest
of the selection content. Downstream code must explicitly request the
`evil_sorter_manual_keep` gate; no existing pipeline default is silently
changed.

Python consumers can use `evil_sorter.selection.load_manual_keep(...)`, which
rejects incomplete reviews by default.

## Data access

The app reads compact catalog rows from the valence session atlas and loads one
cell at a time from the mounted Tachyon outputs. It never copies HDF5 recordings
or writes into successful `evil_caiman` analyses.

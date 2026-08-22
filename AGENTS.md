# Evil Sorter invariants

- Treat all evil_caiman and TeamDMVV inputs as read-only.
- Identify every cell by immutable `(analysis_id, run_id, component_id)`.
- `native_accepted` is the review universe for two-photon data; manual review is
  an additional decision layer and never rewrites CaImAn acceptance.
- Save live decisions atomically to the local SQLite database and export a
  versioned downstream-selection JSON into evil_caiman.
- Never include mice listed in the configured valence exclusion registry.
- Never write inside a run carrying `_SUCCESS`.


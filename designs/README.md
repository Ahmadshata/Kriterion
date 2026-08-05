# Kriterion dashboard concepts

Open `dashboard-concepts.html` in a browser and use the selector at the top to compare all four directions.

1. **Clarity** — balanced, light enterprise interface with strong information hierarchy. Recommended.
2. **Signal Room** — dark, dense operational console for technical reviewers.
3. **Folio** — calm, editorial evidence ledger that emphasizes trust and readability.
4. **Spectral** — near-black spatial interface inspired by SurrealDB's technical visual language, adapted for Kriterion rather than copied.

These are self-contained design prototypes. They use fictional candidate identifiers, make no network requests, and do not change the generated production dashboard. The selected visual system can be ported into `generate_html_report()` after review.

On macOS, regenerate the visual previews with:

```bash
swift designs/render_previews.swift designs/dashboard-concepts.html designs/previews
```

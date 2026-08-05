# Changelog

All notable changes to Kriterion are documented here. This project follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] - 2026-08-05

### Added

- Reintroduced the project as Kriterion, with a dedicated Python package,
  foreground webserver, streamlined launcher, and profile-based workflow.
- Added deterministic experience-only keyword screening, synonym expansion,
  managed-platform relationships, overlap-safe experience calculations, and
  explicit PASS, FAIL, and AMBIGUOUS outcomes.
- Added an interactive HTML dashboard with outcome filters, evidence panels,
  career timelines, screening restrictions, coverage charts, failure-reason
  charts, and a scroll-driven CV screening animation.
- Added ambiguity-only GitHub Copilot recommendations backed by quotations that
  Kriterion verifies against parsed work-experience text before displaying.
- Added reviewer-controlled final PASS or FAIL decisions without overwriting the
  original deterministic result.
- Added incremental scan caching, organized candidate output folders, extracted
  evidence storage, and CSV, Markdown, Excel, and HTML reports.
- Added reusable GitHub Copilot and Claude agents and skills for creating
  profiles and screening CV batches.
- Added automated tests for screening semantics, the local server, launcher,
  dashboard contracts, and design concepts.

### Changed

- Replaced the interactive installation launcher with a small foreground-server
  command that defaults to `./cvs`, `./profiles/profile.yaml`, and the current
  directory while accepting explicit overrides.
- Restricted AI review to genuinely ambiguous results; deterministic passes and
  failures remain code-driven.
- Limited accepted AI evidence to parsed work experience, excluding standalone
  skills, certifications, education, courses, and projects.
- Redesigned the report as a modern responsive interface with dark and light
  themes, animated branding, real aggregate metrics, and accessible fallbacks
  for reduced-motion and compact displays.

### Security

- Bound the report server to loopback and protected AI and decision endpoints
  with a random per-session token.
- Added strict JSON validation, evidence anchoring, scope enforcement, automatic
  retry handling, and conservative failure behavior for AI recommendations.
- Kept extracted CV data and deterministic processing local except when an
  ambiguous candidate is explicitly eligible for Copilot review.

### Removed

- Removed the legacy Resume Triage entry points and branding from the Kriterion
  product tree.

## [0.1.0] - 2026-01-16

### Added

- Added the original local CV screening engine and dependency set.
- Added education-program exclusion from professional experience totals.
- Added CSV, Markdown, and Excel reporting with bucketed candidate outputs.
- Added configurable keywords, CLI overrides, date parsing improvements, and an
  interactive runner.

[Unreleased]: https://github.com/Ahmadshata/Kriterion/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/Ahmadshata/Kriterion/compare/v0.1.0...v0.4.0
[0.1.0]: https://github.com/Ahmadshata/Kriterion/releases/tag/v0.1.0

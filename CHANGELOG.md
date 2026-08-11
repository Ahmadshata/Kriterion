# Changelog

All notable changes to Kriterion are documented here. This project follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Added an on-demand Interview Architect that identifies ambiguous evidence, strong claims,
  career gaps, overlaps, and date conflicts, then generates one verified question and
  Listen-for guide for each distinct issue.
- Added a reversible `--ai-provider codex|copilot` switch, with Codex temporarily
  selected by default for output testing and provider-aware cache invalidation.

### Changed

- Interview Architect and AI Profile Critic are merged into one cached passed-candidate
  issue-and-question analysis with a single dashboard action.
- Strong Claims now prioritizes quantified performance, reliability, delivery, cost,
  latency, and scale assertions and probes how each number was measured, achieved,
  tested, sustained, and attributed to the candidate.
- AI verdict now explains pass/fail screening reasons with verified work-experience
  citations where applicable; document-layout diagnostics remain internal and absence-based
  failures no longer require fabricated quotations.
- AI verdict and Interview Architect artifacts now use a
  shared cross-run cache with context fingerprints and safe provider/schema invalidation.
- Interview Architect is available only for deterministic passing candidates, enforced
  in both the report and local API.
- Company-date-title CV layouts now retain employers, Python scripting and automation
  developer roles count as relevant experience, and unbulleted citations stop at the
  matching responsibility instead of spanning the whole experience entry.
- Codex review mode now suppresses GitHub AI Credit UI and stores no usage metadata;
  Copilot mode retains the existing exact-credit display.
- Interview Architect now covers every positive blank-month career gap across the
  complete employment timeline and requires exactly one question per verified gap.
- Career-history rows now display their actual calendar tenure rather than internal
  overlap-allocation months, preventing legitimate overlapping roles from showing `0.0 yr`.
- Profiles now support `include_freelance_experience: true|false`; excluded freelance
  work supplies neither required-skill evidence nor experience years, and the profile
  creation agent now asks for this choice.

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

# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `CONTRIBUTING.md` (development setup, PCI ground rules, PR process).
- This `CHANGELOG.md`.
- A more specific README with a "Why this tool" before/after and a Roadmap.

### Planned
- Optional concurrent pagination (current version is sequential).
- NDJSON / streaming output for very large stores.
- Resume / checkpoint by cursor for interrupted exports.

## [0.1.0] - 2026-06-08

### Added
- Initial public release.
- `orders` sub-command: orders with non-sensitive `OrderTransaction` metadata,
  CSV/JSON/both output, `--since` / `--until`, `--dry-run`.
- `abandoned-checkouts` sub-command with the recovery URL.
- PCI-safe by design: no `paymentDetails` / card fields are ever selected; a
  response denylist scrubs every payload before writing.
- Read-only Shopify Admin GraphQL client with leaky-bucket throttle handling,
  bounded retries/back-off, and Relay cursor pagination.
- Offline test suite (synthetic fixtures, fake HTTP transport) and GitHub
  Actions CI on Python 3.11 / 3.12.
- MIT license.

[Unreleased]: https://github.com/RAmuSelo/shopify-export-gap-filler/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/RAmuSelo/shopify-export-gap-filler/releases/tag/v0.1.0

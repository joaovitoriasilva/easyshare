# Copilot Coding Guidelines

## Commits logic

Committing should use clear messages following [Conventional Commits](https://www.conventionalcommits.org/) format:

**Format:** `<type>(<scope>)!: <description>` — `(<scope>)` and the breaking-change `!` are optional.

The following rules are enforced automatically on every PR (against the PR title and every commit subject) by `.forgejo/workflows/conventional-commits.yml`. Validation follows the [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/) spec, with a single project-policy addition (the allowed-type whitelist). Generated commit messages must comply:

- **Header format:** `<type>(<scope>)!: <description>` — the `(<scope>)` and breaking-change `!` are optional, and a space is required after the colon.
- **Allowed types (project policy):** `build`, `chore`, `ci`, `docs`, `feat`, `fix`, `perf`, `refactor`, `revert`, `style`, `test`. Types are matched case-insensitively per the spec.
- **Scope** (optional) is any non-empty string (no parentheses), per the spec.
- **Description** is free-form text, per the spec (no lowercase requirement, no trailing-period restriction, no length limit).
- **Breaking changes** are marked with `!` after the type/scope (e.g. `feat(api)!: ...`) or a `BREAKING CHANGE:` footer in the commit body.

Examples:
- `feat: add GPX max speed parsing`
- `fix(garmin): handle multi-segment GPX distance correctly`
- `docs: update development instructions`
- `test(activities): add regression test for GPX segment handling`
- `refactor(api)!: rename Activity.distance to total_distance`

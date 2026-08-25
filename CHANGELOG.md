# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.1] - 2026-08-25

### Added

- Frontend and backend GlitchTip crash reporting integration.
- Forgejo Actions workflow for building and publishing multi-arch Docker images.
- GitHub Actions workflows for CI, Docker image creation, and OpenAPI types drift checks.
- Dependabot configuration for managing dependencies across backend, frontend, Docker, and GitHub Actions.
- `FUNDING.yml` to support various funding platforms.
- README updates with new features, CI changes, and UI screenshots.

### Changed

- Renamed the CSP report URI variable to `EASYSHARE_CSP_REPORT_URI_FRONTEND`.
- Removed unnecessary permissions from workflow files.
- Updated backend and frontend dependencies.

### Fixed

- Renamed CSP report URI variable in `.env.example` to match the frontend variable.
- Removed unnecessary `sudo` from system library installation in the backend CI workflow.
- Fixed `api.generated.ts` generation logic.
- Backend CI audit comments and ignored an additional vulnerability.
- `tool.uv` required-version to allow a compatible resolver range.

## [0.6.0] - 2026-07-21

### Added

- Shared pagination utility for package listing.
- Folder selection for package creation with improved drag-and-drop UI.
- Buffered auditing for share downloads for better performance.
- `iter_objects` method on `StorageBackend`, implemented for the local and S3 backends.
- Node.js engine requirement declaration.

### Changed

- Updated dependencies and refactored imports.
- Enhanced CSS styles across components.

## [0.5.1] - 2026-07-20

### Added

- Contributing guidelines, license, and security policy.
- Codeberg link in the footer.

### Changed

- Exempted `safeuploads` from the supply-chain cooling-off policy.
- Backend upgraded to Python 3.14.
- Moved CI workflows into the `.forgejo` folder.

## [0.5.0] - 2026-07-20

### Added

- Resumable uploads with transfer rate display.

### Changed

- Ignored dev notes directories in `.gitignore`.

## [0.4.0] - 2026-07-20

### Added

- SMTP settings and share verification options in service settings.
- QR code download functionality.
- Health check for the rate limit store.
- Chunked uploads support with an improved file upload experience.

### Changed

- Default per-user storage quota updated to 1 GiB; added max-body-size middleware.
- Optimistic UI updates for file removal actions.
- Improved UI responsiveness across various views.

## [0.3.0] - 2026-07-20

### Added

- Enhanced file management features.

### Changed

- Integrated router for package navigation and streamlined the package creation flow.

### Fixed

- Added a border to button variants for improved styling.

## [0.2.1] - 2026-07-19

### Added

- Pluggable storage backend with a distributed deployment profile (rejecting SQLite in distributed mode).
- Pagination for the packages dashboard.
- Upload progress with drag-and-drop, and a `useUploads` composable for progress tracking.
- Early rejection of over-quota uploads.
- Distributed docker-compose example.
- Skeleton loaders replacing loading text.
- Favicon and web app manifest for improved branding.
- Admin settings view with enhanced user management.
- Enhanced password reset and validation for user management.
- Generated OpenAPI client logic.

### Changed

- Default per-user storage quota set to 10 GiB.
- Improved input placeholders in Login and Register views.
- Enhanced upload item display and action buttons in the package view.

### Fixed

- Session-expiry redirect, upload size check, and streamed owner downloads.
- Corrected status code for entity-too-large errors to `413 Content Too Large`.

## [0.2.0] - 2026-07-17

### Added

- Storage quota management for users.

### Changed

- Updated the theme initialization script.

## [0.1.3] - 2026-07-17

### Added

- Archive download functionality with improved error handling via request IDs.
- Audit log retention and pruning.
- Storage name obfuscation configuration.

### Changed

- Switched password hashing to Argon2id and expanded file storage options.
- Removed debug configuration and updated related documentation.

### Fixed

- Corrected `EASYSHARE_OBFUSCATE_STORAGE_NAMES` syntax in the docker-compose example.
- Added missing `EASYSHARE_FORWARDED_ALLOW_IPS` configuration in the docker-compose example.

## [0.1.2] - 2026-07-16

### Added

- Package statistics and bulk file actions.

## [0.1.1] - 2026-07-16

### Added

- Restart policy for the `easyshare` service in the docker-compose example.

### Changed

- Renamed the docker-compose service from `app` to `easyshare`.
- Widened `package_files.size` to `BigInteger` to support larger files.
- Refactored code structure for improved readability and maintainability.

## [0.1.0] - 2026-07-16

### Added

- Initial release of EasyShare, a secure package sharing application.
- Argon2 password hashing for improved login security.
- Liveness and readiness probes with health checks for backend and frontend.

### Changed

- Hardened Docker images with improved user permissions and security, then consolidated frontend and backend into a single image.
- Minor UI polish (padding, spacing, footer year display).

[0.6.1]: https://github.com/joaovitoriasilva/easyshare/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/joaovitoriasilva/easyshare/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/joaovitoriasilva/easyshare/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/joaovitoriasilva/easyshare/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/joaovitoriasilva/easyshare/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/joaovitoriasilva/easyshare/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/joaovitoriasilva/easyshare/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/joaovitoriasilva/easyshare/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/joaovitoriasilva/easyshare/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/joaovitoriasilva/easyshare/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/joaovitoriasilva/easyshare/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/joaovitoriasilva/easyshare/releases/tag/v0.1.0

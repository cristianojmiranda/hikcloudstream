# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.3] - 2026-06-14

### Changed

- **HLS segment progress** — replace directory glob with O(1) sequential file polling (`_SegmentWatcher`); handles rolling-window segment deletion correctly

## [0.1.2] - 2026-06-13

### Added

- **HLS fMP4 sink** (`stream/sinks/hls.py`) — remux live Annex B H.264 to rolling fMP4 segments via FFmpeg (`-c copy`), with segment progress callbacks for multi-viewer fan-out (e.g. GATO gate viewer POC)
- Unit tests for HLS output-dir cleanup and FFmpeg remux argument wiring

### Changed

- Minimum Python version is now **3.12** (drop 3.11; CI tests 3.12–3.14)
- **MJPEG sink** — configurable `jpeg_quality`, `max_width`, and `require_keyframe`; higher default substream width (1408); 4:4:4 subsampling at quality ≥ 90 to reduce color banding

## [0.1.1] - 2026-06-09

### Added

- PyPI publication (`pip install hikcloudstream`)
- GitHub Actions workflow for publishing on version tags

## [0.1.0] - 2026-06-09

### Added

- Initial public release migrated from sandbox prototype
- `HikConnectClient` — login, list cameras, cloud snapshot
- `hikcloudstream.stream` — VTM live sessions, auto stream probe, MPEG-TS record, MJPEG viewer
- CLI: `hikcloudstream-snapshot`, `hikcloudstream-stream`
- Examples, docs, unit tests, GitHub Actions CI

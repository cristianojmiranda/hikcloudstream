# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Zone capture** — `Zone`, `capture_zone_snapshot()`, `record_zone_stream()` and CLI `--zone X,Y,W,H` crop a normalized area of the live image without moving the camera
- **PTZ presets** — `HikConnectClient.goto_preset()` / `list_presets()`, `capture_preset_snapshot()`, `record_preset_stream()` and CLI `--zone-preset`, `--home-preset`, `--ptz-settle`, `--list-presets`; the home preset is always recalled, `PTZRestoreError` is raised if it fails three times
- **Encrypted MPEG-PS/HEVC** — `decrypt_key` on HLS and MPEG-TS sinks; the HLS proxy transcodes decrypted video to H.264
- CLI reads `.env` from the current directory and `HIK_CONNECT_VALIDATE_CODE`; the camera number can be the only positional argument

### Changed

- CLI `--duration` default is now 15s; zero or negative durations are rejected
- Recordings are staged in a temporary file and must contain a decodable frame before replacing the output
- MJPEG viewer rejects encrypted streams (use HLS)

### Security

- Login and auth redirects are restricted to HTTPS `hik-connect.com` / `ezvizlife.com` origins; HTTP redirects are no longer followed automatically
- API payloads are no longer included in error messages
- Viewer HTML escapes camera names; HLS file serving uses a strict path containment check

## [0.1.4] - 2026-06-14

### Added

- **HLS browser viewer** in `hikcloudstream-stream --proxy` — default `--player hls` (hls.js + FFmpeg fMP4 passthrough); `--player mjpeg` remains for legacy preview
- **`hls_stream_candidates()`** — ordered ingest list with SD substream fallback when `--main-stream` is forced and substream probe succeeds; main-only cameras (e.g. channel 17) never get a substream candidate
- CLI flags: `--preview-fps`, `--jpeg-quality`, `--max-width` for MJPEG tuning

### Changed

- **`serve_stream_proxy`** — HLS bootstrap with genpts/wallclock timestamps, longer main-stream ready timeout, and on-page fallback notice when main decode fails

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

# hikcloudstream

[![CI](https://github.com/cristianojmiranda/hikcloudstream/actions/workflows/ci.yml/badge.svg)](https://github.com/cristianojmiranda/hikcloudstream/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/hikcloudstream.svg)](https://pypi.org/project/hikcloudstream/)
![Python](https://img.shields.io/badge/python-3.12%2B-blue)
![License](https://img.shields.io/badge/license-Apache--2.0-green)

**Unofficial** Python SDK for **Hik-Connect cloud cameras** — list devices, cloud snapshots, and live streaming over the VTM relay.

> If you have Hik-Connect cameras in the cloud (condo, shared NVR, no RTSP URL) and found almost nothing on GitHub — that's why this exists. This is a **community library**, not an official Hikvision or EZVIZ product. APIs can change without notice.

## What it does

- Log in with your Hik-Connect account (same credentials as the mobile app)
- List cameras and channels on the account
- Cloud snapshot (~352×288 thumbnail via API)
- **Live stream** via cloud VTM relay (H.264 → Annex B, MPEG-TS, HLS fMP4, MJPEG viewer)
- Auto-select substream vs main stream per camera

## What it does **not** do

- LAN RTSP / ONVIF / ISAPI (use FFmpeg, go2rtc, or HCNetSDK for local NVR access)
- P2P hole-punching (the app uses P2P at home; remote cloud preview uses **VTM relay** — same path as this library)
- Official support or guaranteed API stability

## Quick start

```bash
pip install "hikcloudstream[viewer]"
# or from source:
git clone https://github.com/cristianojmiranda/hikcloudstream.git
cd hikcloudstream && uv sync --extra viewer
```

```python
from hikcloudstream import Credentials, HikConnectClient

with HikConnectClient() as client:
    client.login(Credentials("user@example.com", "your_password"))
    for cam in client.list_cameras():
        print(cam.index, cam.name, cam.device_serial, cam.channel_no)
```

## Install

| Extra | Purpose | Command |
|-------|---------|---------|
| core | API + streaming protocol | `pip install hikcloudstream` |
| `cli` | Command-line tools + Pillow | `pip install "hikcloudstream[cli]"` |
| `viewer` | MJPEG HTTP viewer (PyAV) | `pip install "hikcloudstream[viewer]"` |
| `dev` | Tests, ruff, mypy | `uv sync --extra dev` |

**System dependency:** [FFmpeg](https://ffmpeg.org/) (`ffmpeg` on PATH) for recording, HD frame capture, MPEG-TS remux, and HLS fMP4 segment generation.

## CLI

```bash
export HIK_CONNECT_USER="user@example.com"
export HIK_CONNECT_PASSWORD="your_password"

uv run hikcloudstream-snapshot "$HIK_CONNECT_USER" "$HIK_CONNECT_PASSWORD" --list
uv run hikcloudstream-snapshot "$HIK_CONNECT_USER" "$HIK_CONNECT_PASSWORD" 1 -o thumb.jpg
uv run hikcloudstream-stream "$HIK_CONNECT_USER" "$HIK_CONNECT_PASSWORD" 1 --proxy
uv run hikcloudstream-stream "$HIK_CONNECT_USER" "$HIK_CONNECT_PASSWORD" 1 -o frame.jpg --duration 6s
```

Open `http://127.0.0.1:8558/` in a browser when using `--proxy`.

## Stream types

| `stream=` | Typical use |
|-----------|-------------|
| **2** (substream) | Lower bandwidth, standard H.264 — works on most DVR channels |
| **1** (main) | Higher resolution; some cameras only expose this stream |
| **auto** (default) | Probes substream for 5s, falls back to main |

Force main stream in Python: `StreamType.MAIN`. In CLI: `--main-stream`.

## Examples

See [`examples/`](examples/) — each script documents required extras and env vars.

## Documentation

- [Quickstart](docs/quickstart.md)
- [Streaming API](docs/streaming.md)
- [Limitations](docs/limitations.md)
- [Architecture](docs/architecture.md)

## Origin

Live streaming was reverse-engineered from the **Hik-Connect for End User** mobile app and aligned with [pyezvizapi](https://github.com/RenierM26/pyEzvizApi). The implementation uses the **cloud VTM relay protocol**.

## Related projects

- [pyezvizapi](https://github.com/RenierM26/pyEzvizApi) — VTM protocol (Apache-2.0)
- [Home Assistant EZVIZ](https://www.home-assistant.io/integrations/ezviz/) — integration using pyezvizapi
- [go2rtc](https://github.com/AlexxIT/go2rtc) — LAN RTSP/WebRTC aggregator

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). AI agents: read [AGENT.md](AGENT.md) first.

## Legal disclaimer

This is an **unofficial** community project. It is **not** affiliated with, endorsed by, or supported by Hangzhou Hikvision Digital Technology Co., Ltd. or EZVIZ. Use at your own risk. You are responsible for complying with Hik-Connect / EZVIZ Terms of Service and applicable law. Trademarks belong to their respective owners.

## License

Apache-2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).

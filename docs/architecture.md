# Architecture

High-level data flow (no internal endpoint catalog):

```
┌─────────────┐     REST      ┌──────────────────┐
│  Your app   │ ────────────► │ HikConnectClient │
│  or CLI     │               │  (httpx)         │
└──────┬──────┘               └────────┬─────────┘
       │                               │
       │ stream                        │ sessionId
       ▼                               ▼
┌──────────────────┐  VTDU tokens  ┌─────────────────┐
│ LiveStreamSession│ ◄──────────── │ stream/adapter  │
└────────┬─────────┘               └─────────────────┘
         │ ysproto://VTM:8554
         ▼
┌──────────────────┐   RTP H.264   ┌──────────────────┐
│ pyezvizapi VTM   │ ────────────► │ stream/rtp       │
│ client           │               │ stream/sinks/*   │
└──────────────────┘               └──────────────────┘
```

## Package layout

```
src/hikcloudstream/
├── client.py          # REST API
├── capture.py         # Snapshot decrypt
├── stream/
│   ├── session.py     # VTM lifecycle
│   ├── probe.py       # Auto stream type
│   ├── rtp.py         # Depacketization
│   ├── crypto.py      # Encrypted NAL
│   └── sinks/         # MPEG-TS, HLS fMP4, MJPEG, HTTP
└── cli/               # Optional commands
```

## Dependencies

- **httpx** — REST
- **pyezvizapi** — VTM TCP protocol
- **pycryptodome** — AES for snapshots and encrypted streams
- **av** (optional) — PyAV MJPEG decoder
- **FFmpeg** (system) — MPEG-TS remux, HLS fMP4 segments, frame extract

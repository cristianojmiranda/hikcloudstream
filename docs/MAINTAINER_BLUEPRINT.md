# Maintainer blueprint

Internal planning notes for **hikcloudstream** maintainers. The public README is the user-facing source of truth.

## Protocol clarification

Live video uses **cloud VTM relay**, not LAN RTSP and not classic P2P hole-punching:

```
Account login (REST)
    → device/channel discovery (pagelist + VTM metadata)
    → VTDU stream tokens
    → TCP session to regional VTM server (ysproto://…)
    → RTP carrying H.264
    → depacketize / decode / remux
```

The Hik-Connect mobile app also uses VTM for remote preview when P2P/LAN is unavailable. Do **not** describe this project as a “P2P stream fix.”

## Trade-offs

| Decision | Pros | Cons |
|----------|------|------|
| Build on pyezvizapi | Battle-tested VTM framing | Hik-Connect adapter layer forever |
| VTM-only (no P2P) | Matches cloud condo use case | No LAN optimizations |
| PyAV for MJPEG | Low latency | Heavy optional dep; CPU per viewer |
| Auto stream probe | Works across DVR channels | ~5s connect delay |
| Alpha 0.x semver | API flexibility | Breaking changes possible |

## License, copyright, and open-source safety

> Not legal advice.

Publishing as unofficial OSS is **reasonable** (same category as pyezvizapi, Home Assistant EZVIZ). Main risks: **ToS**, **trademark**, **secrets in repo** — not “you cannot copyright your Python.”

| Do | Don't |
|----|-------|
| Apache-2.0 + NOTICE | APK decompile, SDK blobs |
| README disclaimer | Official logos / “Hikvision SDK” naming |
| Placeholder examples | Real credentials or device serials |

See README legal disclaimer. Confirm employer IP if applicable.

## Deferred (post-0.1.1)

- Async API (`httpx.AsyncClient`)
- P2P / LAN RTSP
- Encrypted live MJPEG viewer
- Home Assistant integration
- Dependabot, SECURITY.md, integration CI nightly

## Public API stability

Exports in `hikcloudstream/__init__.py` and `hikcloudstream/stream/__init__.py` are the stable surface for 0.1.x. Breaking changes require CHANGELOG entry.

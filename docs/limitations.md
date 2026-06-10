# Limitations

| Issue | Impact | Workaround |
|-------|--------|------------|
| Unofficial API | Endpoints may change | Pin `ClientConfig.client_version`; watch app updates |
| VTM session limits | N viewers = N cloud connections | Single ingest + HLS/WebRTC fan-out |
| Encrypted live MJPEG | Viewer raises error | `validate_code` on record/snapshot only |
| Proprietary RTP on main | Some channels black on `stream=1` | Auto substream (`stream=2`) |
| Channels without VTM | `Could not find VTM resource` | Channel offline or unlicensed |
| Cloud snapshot resolution | Fixed ~352×288 | Live frame capture for HD |
| CAPTCHA / 2FA | Login fails | Log in via official app first |
| No P2P / LAN RTSP | No direct NVR URL | Use go2rtc / RTSP for local access |
| Token / firewall | VTDU auth blocked | Ensure outbound HTTPS to Hik-Connect auth hosts |

## Performance (single viewer)

Approximate values — vary by CPU, camera, and stream type:

| Profile | RAM | Egress |
|---------|-----|--------|
| Substream MJPEG | ~65 MB | ~0.7 Mbps |
| Main HD MJPEG | ~100 MB | ~10–15 Mbps |

Not suitable for 50+ viewers without architecture change — see [streaming.md](streaming.md).

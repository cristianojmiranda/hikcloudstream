"""Keep packetized MPEG transports intact during live ingest."""

from types import SimpleNamespace

from pyezvizapi.stream import StreamTransport, VtmChannel

from hikcloudstream.stream.sinks import annex_b
from hikcloudstream.stream.sinks.mpegts import ffmpeg_input_format


class FakeStream:
    def __init__(self, bodies: list[bytes]) -> None:
        self.bodies = bodies

    def iter_packets(self, *, max_packets: int | None = None):
        for body in self.bodies[:max_packets]:
            yield SimpleNamespace(channel=VtmChannel.STREAM, encrypted=False, body=body)


def test_mpeg_ps_fragments_keep_original_bytes(monkeypatch) -> None:
    first = b"\x00\x00\x01\xba" + b"header"
    second = b"\x00\x00\x00\x01\x65" + b"fragment"
    monkeypatch.setattr(
        annex_b,
        "detect_transport",
        lambda body: StreamTransport.MPEG_PS if body is first else StreamTransport.RTP,
    )

    chunks = list(annex_b.iter_annex_b_chunks(FakeStream([first, second])))

    assert chunks == [
        (StreamTransport.MPEG_PS, first),
        (StreamTransport.MPEG_PS, second),
    ]


def test_ffmpeg_uses_correct_mpeg_input_formats() -> None:
    assert ffmpeg_input_format(StreamTransport.MPEG_PS) == "mpeg"
    assert ffmpeg_input_format(StreamTransport.MPEG_TS) == "mpegts"

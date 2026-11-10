"""Zone validation and image crop tests."""

import io

import pytest
from PIL import Image

from hikcloudstream.stream.zone import Zone, crop_jpeg


def test_zone_rejects_out_of_frame() -> None:
    with pytest.raises(ValueError):
        Zone.parse("0.8,0.2,0.4,0.5")
    with pytest.raises(ValueError):
        Zone.parse("0,0,0,1")


def test_crop_jpeg_selects_expected_region() -> None:
    image = Image.new("RGB", (100, 80), "red")
    image.paste("blue", (50, 0, 100, 80))
    source = io.BytesIO()
    image.save(source, format="JPEG")
    result = crop_jpeg(source.getvalue(), Zone.parse("0.5,0,0.5,1"))
    with Image.open(io.BytesIO(result)) as cropped:
        assert cropped.size == (50, 80)
        r, g, b = cropped.getpixel((25, 40))
        assert b > r and b > g

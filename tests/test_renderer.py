from unittest.mock import MagicMock

from PIL import Image, ImageFont
from print_server.renderer import (
    box_size,
    code128,
    fit_font,
    fit_text,
    render,
    round_box,
)


def test_box_size() -> None:
    box = ((10.0, 20.0), (50.0, 60.0))
    # y1-y0 = 50-10 = 40
    # x1-x0 = 60-20 = 40
    assert box_size(box) == (40.0, 40.0)


def test_round_box() -> None:
    box = ((10.1, 20.6), (49.9, 60.4))
    # round(10.1)=10, round(20.6)=21
    # round(49.9)=50, round(60.4)=60
    assert round_box(box) == ((10, 21), (50, 60))


def test_fit_font() -> None:
    # Test that it returns a font object
    # The actual size depends on the font file which is bundled
    size = (100.0, 200.0)
    font = fit_font(size, "TEST")
    assert isinstance(font, ImageFont.FreeTypeFont)

    # Ensure it fits
    bbox = font.getbbox("TEST")
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    assert text_w < size[1]
    assert text_h < size[0]


def test_fit_text() -> None:
    # Mock ImageDraw
    draw = MagicMock()
    box = ((0.0, 0.0), (100.0, 200.0))
    text = "TEST LABEL"

    fit_text(draw, box, text)

    # Verify draw.text was called
    draw.text.assert_called_once()
    args, kwargs = draw.text.call_args
    # args[0] is position (x, y)
    # args[1] is text
    assert args[1] == text
    assert "font" in kwargs
    assert isinstance(kwargs["font"], ImageFont.FreeTypeFont)


def test_code128() -> None:
    s = "123456"

    # Just a smoke test to ensure it generates an image
    # We pass pixel dimensions
    size_px = (100.0, 300.0)
    img = code128(s, size_px)

    assert isinstance(img, Image.Image)


def test_render_smoke() -> None:
    # Smoke test to ensure render runs without crashing
    label = {
        "package_id": "PKG123",
        "inmate_id": "12345",
        "inmate_name": "John Doe",
        "inmate_jurisdiction": "County",
        "unit_name": "Block A",
        "unit_shipping_method": "Truck",
    }
    img = render(label)
    assert isinstance(img, Image.Image)
    assert img.size == (1300, 500)

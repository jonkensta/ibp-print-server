import pytest
from PIL import Image, ImageDraw
from print_server.renderer import box_size, round_box, fit_font, render, fit_text

def test_box_size():
    box = ((10, 20), (50, 60))
    # y1-y0 = 50-10 = 40
    # x1-x0 = 60-20 = 40
    assert box_size(box) == (40, 40)

def test_round_box():
    box = ((10.1, 20.6), (49.9, 60.4))
    # round(10.1)=10, round(20.6)=21
    # round(49.9)=50, round(60.4)=60
    assert round_box(box) == ((10, 21), (50, 60))

def test_fit_font():
    # Test that it returns a font object
    # The actual size depends on the font file which is bundled
    size = (100, 200)
    font = fit_font(size, "TEST")
    assert font is not None
    
    # Ensure it fits
    bbox = font.getbbox("TEST")
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    # Our fit_font logic ensures text_h < size_h and text_w < size_w
    # NOTE: The loop finds the max size where it fits, or min if it never fits well,
    # but with (100, 200) it should definitely fit.
    assert text_w < size[1]
    assert text_h < size[0]

def test_render_smoke():
    # Smoke test to ensure render runs without crashing
    label = {
        "package_id": "PKG123",
        "inmate_id": "12345",
        "inmate_name": "John Doe",
        "inmate_jurisdiction": "County",
        "unit_name": "Block A",
        "unit_shipping_method": "Truck"
    }
    img = render(label)
    assert isinstance(img, Image.Image)
    assert img.size == (1300, 500)

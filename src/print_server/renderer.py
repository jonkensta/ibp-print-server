import importlib.resources
from typing import Tuple, Dict

import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont


def code128(s: str, size: Tuple[float, float]) -> Image.Image:
    """Generate a Code128 barcode image."""
    writer = ImageWriter()
    # dpi=300 is standard for print
    options = dict(write_text=False, writer=writer, dpi=300, quiet_zone=0)

    def px2mm(px):
        return 25.4 * px / options["dpi"]

    # Code128 includes checksum by default
    code = barcode.Code128(str(s), writer=writer)

    raw = code.build()
    modules_per_line = len(raw[0])
    w = px2mm(size[0]) / modules_per_line
    options["module_width"] = w

    h = px2mm(size[1]) - 2  # barcode adds this for some reason
    options["module_height"] = h

    return code.render(options)


def box_size(box):
    (y0, x0), (y1, x1) = box
    return y1 - y0, x1 - x0


def _get_font_file_path() -> str:
    """Retrieve the path to the bundled font file."""
    # This works for Python 3.9+ and handles package resources
    try:
        ref = importlib.resources.files(__package__) / "DejaVuSansMono.ttf"
        with importlib.resources.as_file(ref) as path:
            return str(path)
    except Exception:
        # Fallback for when running outside of package context or earlier python versions if needed,
        # though we specified Python 3.12.
        # But importlib.resources.files is robust.
        return "DejaVuSansMono.ttf"


def get_font_cache() -> Dict[int, ImageFont.FreeTypeFont]:
    """Load and cache fonts of varying sizes."""
    font_path = _get_font_file_path()
    return {
        font_size: ImageFont.truetype(font_path, font_size)
        for font_size in range(1, 100)
    }


# Initialize font cache
_FONTS = get_font_cache()


def fit_font(size: Tuple[float, float], text: str) -> ImageFont.FreeTypeFont:
    size_h, size_w = size

    min_, max_ = 1, 100
    while abs(max_ - min_) > 1:
        font_size = int(round((max_ - min_) / 2)) + min_

        font = _FONTS[font_size]
        # Replacement for getsize using getbbox
        # getbbox returns (left, top, right, bottom)
        bbox = font.getbbox(text)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        if text_h < size_h and text_w < size_w:
            min_ = font_size
        else:
            max_ = font_size

    return _FONTS[min_]


def round_box(box):
    (w0, h0), (w1, h1) = box
    w0, h0, w1, h1 = map(round, (w0, h0, w1, h1))
    w0, h0, w1, h1 = map(int, (w0, h0, w1, h1))
    return (w0, h0), (w1, h1)


def fit_text(draw: ImageDraw.ImageDraw, box, text: str):
    text = str(text)
    lhs, _ = round_box(box)
    size = box_size(box)

    font = fit_font(size, text)
    
    bbox = font.getbbox(text)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # Simple centering based on bbox dimensions
    # Note: text rendering might need adjustment for ascent/descent if strict vertical alignment is needed,
    # but for simple labels this usually suffices.
    x = lhs[0] + round((size[0] - text_w) / 2)
    y = lhs[1] + round((size[1] - text_h) / 2)

    draw.text((x, y), text, font=font)


def add_barcode(image: Image.Image, label: str, box):
    lhs, rhs = round_box(box)
    size = rhs[0] - lhs[0], rhs[1] - lhs[1]
    # Use code128 instead of code39
    bc_img = code128(label, size)
    image.paste(bc_img, lhs)


def render(label: dict) -> Image.Image:
    size = w, h = 1300, 500
    image = Image.new("L", size, color=(255,))
    draw = ImageDraw.Draw(image)

    # package ID barcode
    box = (0.68 * w, 0.00 * h), (1.00 * w, 0.10 * h)
    fit_text(draw, box, "package ID")

    box = (0.68 * w, 0.10 * h), (1.00 * w, 0.50 * h)
    add_barcode(image, label["package_id"], box)

    box = (0.68 * w, 0.50 * h), (1.00 * w, 0.60 * h)
    fit_text(draw, box, label["package_id"])

    # inmate ID barcode
    box = (0.02 * w, 0.00 * h), (0.65 * w, 0.10 * h)
    fit_text(draw, box, "inmate ID")

    box = (0.02 * w, 0.10 * h), (0.65 * w, 0.50 * h)
    add_barcode(image, label["inmate_id"], box)

    box = (0.02 * w, 0.50 * h), (0.65 * w, 0.60 * h)
    fit_text(draw, box, label["inmate_id"])

    # inmate name
    box = (0.00 * w, 0.60 * h), (1.00 * w, 0.90 * h)
    fit_text(draw, box, label["inmate_name"])

    # other info at bottom
    box = (0.00 * w, 0.90 * h), (0.33 * w, 1.00 * h)
    fit_text(draw, box, label["inmate_jurisdiction"])

    box = (0.33 * w, 0.90 * h), (0.67 * w, 1.00 * h)
    fit_text(draw, box, label["unit_name"])

    box = (0.67 * w, 0.90 * h), (1.00 * w, 1.00 * h)
    fit_text(draw, box, label["unit_shipping_method"])

    return image

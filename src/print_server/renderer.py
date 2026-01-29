import importlib.resources
from typing import cast

import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont


def code128(s: str, size: tuple[float, float]) -> Image.Image:
    """Generate a Code128 barcode image."""
    writer = ImageWriter()
    # dpi=300 is standard for print
    options = dict(write_text=False, writer=writer, dpi=300, quiet_zone=0)

    def px2mm(px: float) -> float:
        return 25.4 * px / options["dpi"]  # type: ignore

    # Code128 includes checksum by default
    code = barcode.Code128(str(s), writer=writer)

    raw = code.build()
    modules_per_line = len(raw[0])
    w = px2mm(size[0]) / modules_per_line
    options["module_width"] = w

    h = px2mm(size[1]) - 2  # barcode adds this for some reason
    options["module_height"] = h

    # Cast to Image.Image because barcode.render returns Any
    return cast(Image.Image, code.render(options))


def box_size(
    box: tuple[tuple[float, float], tuple[float, float]],
) -> tuple[float, float]:
    (y0, x0), (y1, x1) = box
    return y1 - y0, x1 - x0


def _get_font_file_path() -> str:
    """Retrieve the path to the bundled font file."""
    try:
        ref = importlib.resources.files(__package__) / "DejaVuSansMono.ttf"
        with importlib.resources.as_file(ref) as path:
            return str(path)
    except Exception:
        return "DejaVuSansMono.ttf"


def get_font_cache() -> dict[int, ImageFont.FreeTypeFont]:
    """Load and cache fonts of varying sizes."""
    font_path = _get_font_file_path()
    return {
        font_size: ImageFont.truetype(font_path, font_size)
        for font_size in range(1, 100)
    }


# Initialize font cache
_FONTS = get_font_cache()


def fit_font(size: tuple[float, float], text: str) -> ImageFont.FreeTypeFont:
    size_h, size_w = size

    min_, max_ = 1, 100
    while abs(max_ - min_) > 1:
        font_size = int(round((max_ - min_) / 2)) + min_

        font = _FONTS[font_size]
        bbox = font.getbbox(text)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        if text_h < size_h and text_w < size_w:
            min_ = font_size
        else:
            max_ = font_size

    return _FONTS[min_]


def round_box(
    box: tuple[tuple[float, float], tuple[float, float]],
) -> tuple[tuple[int, int], tuple[int, int]]:
    (w0, h0), (w1, h1) = box
    w0_r, h0_r, w1_r, h1_r = map(round, (w0, h0, w1, h1))
    return (int(w0_r), int(h0_r)), (int(w1_r), int(h1_r))


def fit_text(
    draw: ImageDraw.ImageDraw,
    box: tuple[tuple[float, float], tuple[float, float]],
    text: str,
) -> None:
    text = str(text)
    lhs, _ = round_box(box)
    size = box_size(box)

    font = fit_font(size, text)

    bbox = font.getbbox(text)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    x = lhs[0] + round((size[0] - text_w) / 2)
    y = lhs[1] + round((size[1] - text_h) / 2)

    draw.text((x, y), text, font=font)


def add_barcode(
    image: Image.Image,
    label: str,
    box: tuple[tuple[float, float], tuple[float, float]],
) -> None:
    lhs, rhs = round_box(box)
    # The image paste expects (int, int), lhs is (int, int) from round_box
    size = float(rhs[0] - lhs[0]), float(rhs[1] - lhs[1])
    bc_img = code128(label, size)
    image.paste(bc_img, lhs)


def render(label: dict[str, str]) -> Image.Image:
    w, h = 1300.0, 500.0
    image = Image.new("L", (int(w), int(h)), color=(255,))
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

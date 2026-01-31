import importlib.resources
from typing import Any, TypedDict, cast

import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont


class BarcodeOptions(TypedDict):
    write_text: bool
    writer: Any
    dpi: int
    quiet_zone: int
    module_width: float
    module_height: float


def code128(s: str, size: tuple[float, float]) -> Image.Image:
    """Generate a Code128 barcode image."""
    writer = ImageWriter()
    # dpi=300 is standard for print
    # We initialize with a dict but will cast or rely on usage
    base_options: BarcodeOptions = {
        "write_text": False,
        "writer": writer,
        "dpi": 300,
        "quiet_zone": 0,
        "module_width": 0.0,  # Placeholder, set later
        "module_height": 0.0,  # Placeholder, set later
    }

    def px2mm(px: float) -> float:
        dpi = base_options["dpi"]
        return 25.4 * px / dpi

    # Code128 includes checksum by default
    code = barcode.Code128(str(s), writer=writer)

    raw = code.build()
    modules_per_line = len(raw[0])
    w = px2mm(size[0]) / modules_per_line
    base_options["module_width"] = w

    h = px2mm(size[1]) - 2  # barcode adds this for some reason
    base_options["module_height"] = h

    # Cast to Image.Image because barcode.render returns Any
    # barcode.render expects Dict[str, Any] usually, but TypedDict should pass as Dict
    return cast(Image.Image, code.render(cast(dict[str, Any], base_options)))


def box_size(
    box: tuple[tuple[float, float], tuple[float, float]],
) -> tuple[float, float]:
    (x0, y0), (x1, y1) = box
    return x1 - x0, y1 - y0


def get_font_cache() -> dict[int, ImageFont.FreeTypeFont]:
    """Load and cache fonts of varying sizes."""
    fonts = {}
    ref = importlib.resources.files(__package__) / "DejaVuSansMono.ttf"
    with importlib.resources.as_file(ref) as path:
        # Load all fonts while the file path is guaranteed to be valid
        for font_size in range(1, 100):
            fonts[font_size] = ImageFont.truetype(str(path), font_size)

    return fonts


# Initialize font cache
_FONTS = get_font_cache()


def fit_font(size: tuple[float, float], text: str) -> ImageFont.FreeTypeFont:
    size_w, size_h = size

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
    (x0, y0), (x1, y1) = box
    x0_r, y0_r, x1_r, y1_r = map(round, (x0, y0, x1, y1))
    return (int(x0_r), int(y0_r)), (int(x1_r), int(y1_r))


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

    w, h = size
    x = lhs[0] + round((w - text_w) / 2) - bbox[0]
    y = lhs[1] + round((h - text_h) / 2) - bbox[1]

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


def render(label: dict[str, str], size: tuple[int, int] = (1050, 420)) -> Image.Image:
    w, h = float(size[0]), float(size[1])
    image = Image.new("L", (int(w), int(h)), color=(255,))
    draw = ImageDraw.Draw(image)

    # package ID barcode (full width)
    box = (0.05 * w, 0.05 * h), (0.95 * w, 0.38 * h)
    add_barcode(image, label["package_id"], box)

    box = (0.05 * w, 0.38 * h), (0.95 * w, 0.48 * h)
    fit_text(draw, box, f"PACKAGE ID: {label['package_id']}".upper())

    # inmate name and ID
    box = (0.05 * w, 0.50 * h), (0.95 * w, 0.75 * h)
    fit_text(draw, box, f"{label['inmate_name']} #{label['inmate_id']}".upper())

    # jurisdiction, unit, shipping
    box = (0.05 * w, 0.77 * h), (0.95 * w, 0.95 * h)
    details = (
        f"{label['inmate_jurisdiction']} \u2014 "
        f"{label['unit_name']} \u2014 "
        f"{label['unit_shipping_method']}"
    ).upper()
    fit_text(draw, box, details)

    return image

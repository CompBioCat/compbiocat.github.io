#!/usr/bin/env python3
"""Generate the site's web-ready images from the full-resolution originals.

Reads   data/images.yml
Sources assets/images/_originals/{people,banner,logos}/
Writes  assets/images/{people,banner,logos}/

Never edit the generated files by hand — this script overwrites them. To change a
crop or swap a photo, edit data/images.yml and re-run:

    python scripts/build_images.py

Requires Pillow and PyYAML.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is missing. Install it with:  python3 -m pip install pyyaml")

try:
    from PIL import Image, ImageFilter, ImageOps
except ImportError:
    sys.exit("Pillow is missing. Install it with:  python3 -m pip install pillow")

# Pillow moved the resampling constants in 9.1; support both.
LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import warn_if_preview_running   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "data" / "images.yml"
SRC = ROOT / "assets" / "images" / "_originals"
OUT = ROOT / "assets" / "images"

warnings: list[str] = []
notes: list[str] = []


def load_source(kind: str, filename: str) -> Image.Image:
    path = SRC / kind / filename
    if not path.exists():
        raise FileNotFoundError(path.relative_to(ROOT))
    img = Image.open(path)
    # Honour EXIF rotation, then drop the tag so it is not applied twice.
    img = ImageOps.exif_transpose(img)
    size_mb = path.stat().st_size / 1_048_576
    limit = CFG["defaults"].get("max_original_mb", 2.5)
    if size_mb > limit:
        warnings.append(
            f"{path.relative_to(ROOT)} is {size_mb:.1f} MB, over the {limit} MB "
            f"guideline for a committed original — consider downsizing it."
        )
    return img


def fractional_crop(img: Image.Image, frac, aspect: float | None) -> Image.Image:
    """Crop using [left, top, width] or [left, top, width, height] as fractions.

    Fractions rather than pixels so that swapping in a higher-resolution version
    of the same photo needs no change to the numbers.
    """
    w, h = img.size
    if len(frac) == 4:
        left, top, fw, fh = frac
        box_w, box_h = fw * w, fh * h
    else:
        left, top, fw = frac
        box_w = fw * w
        box_h = box_w / (aspect or 1.0)
    x0, y0 = left * w, top * h
    # Keep the box inside the image rather than failing on a slightly-off number.
    x0 = max(0, min(x0, w - 1))
    y0 = max(0, min(y0, h - 1))
    box_w = min(box_w, w - x0)
    box_h = min(box_h, h - y0)
    return img.crop((round(x0), round(y0), round(x0 + box_w), round(y0 + box_h)))


def default_square_crop(img: Image.Image, aspect: float) -> Image.Image:
    """Largest box of the given aspect, anchored to the top edge, centred.

    Right for a head-and-shoulders shot: keeps the head, trims the sides.
    """
    w, h = img.size
    box_h = h
    box_w = box_h * aspect
    if box_w > w:
        box_w = w
        box_h = box_w / aspect
    x0 = (w - box_w) / 2
    return img.crop((round(x0), 0, round(x0 + box_w), round(box_h)))


def apply_treatment(img: Image.Image, treatment: str) -> Image.Image:
    img = img.convert("RGB")
    if treatment == "grayscale":
        img = ImageOps.grayscale(img)
        # Very mild black/white point normalisation so photos shot under
        # different lighting sit at a comparable tonal range. Deliberately gentle
        # — this is levelling, not retouching.
        img = ImageOps.autocontrast(img, cutoff=(1, 1))
        img = img.convert("RGB")
    return img


def save_variants(img: Image.Image, out_dir: Path, slug: str, widths, quality: int,
                  upscale_from: int | None = None) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    src_w = img.size[0]
    for width in sorted(widths):
        # Smallest width -> "<slug>.jpg" (1x), largest -> "<slug>@2x.jpg" (retina)
        name = f"{slug}.jpg" if width == min(widths) else f"{slug}@2x.jpg"
        scale = width / src_w
        target = (width, max(1, round(img.size[1] * scale)))
        resized = img.resize(target, LANCZOS)
        if scale > 1.0:
            # Upscaling loses definition; a light unsharp compensates a little.
            resized = resized.filter(
                ImageFilter.UnsharpMask(radius=1.0, percent=60, threshold=3)
            )
        path = out_dir / name
        resized.save(path, "JPEG", quality=quality, optimize=True,
                     progressive=True, subsampling=1)
        written.append(f"{path.relative_to(ROOT)}  {target[0]}x{target[1]}")
    if upscale_from is not None and upscale_from < max(widths):
        warnings.append(
            f"{slug}: source is only {upscale_from}px wide after cropping, but the "
            f"2x version is {max(widths)}px — it is upscaled and will look soft. "
            f"A higher-resolution original would fix this."
        )
    return written


def build_people() -> None:
    d = CFG["defaults"]
    aspect = float(d.get("portrait_aspect", 1.0))
    widths = d.get("portrait_widths", [220, 440])
    print("Portraits")
    for slug, spec in CFG.get("people", {}).items():
        try:
            img = load_source("people", spec["source"])
        except FileNotFoundError as exc:
            warnings.append(f"{slug}: original missing ({exc}) — no image generated.")
            print(f"  {slug:<22} MISSING SOURCE")
            continue
        cropped = (fractional_crop(img, spec["crop"], aspect)
                   if spec.get("crop") else default_square_crop(img, aspect))
        treated = apply_treatment(cropped, d.get("treatment", "grayscale"))
        written = save_variants(treated, OUT / "people", slug, widths,
                                d.get("quality", 82),
                                upscale_from=cropped.size[0])
        print(f"  {slug:<22} from {spec['source']:<24} crop {cropped.size[0]}x{cropped.size[1]}")
        if spec.get("note"):
            notes.append(f"{slug}: {' '.join(spec['note'].split())}")


def build_banner() -> None:
    d = CFG["defaults"]
    print("Group photo")
    for slug, spec in CFG.get("banner", {}).items():
        try:
            img = load_source("banner", spec["source"])
        except FileNotFoundError as exc:
            warnings.append(f"{slug}: original missing ({exc}) — no image generated.")
            print(f"  {slug:<22} MISSING SOURCE")
            continue
        cropped = fractional_crop(img, spec["crop"], None)
        # a per-entry `treatment:` overrides the global default
        treated = apply_treatment(cropped, spec.get("treatment",
                                                    d.get("treatment", "grayscale")))
        widths = spec.get("widths", [1200, 2400])
        save_variants(treated, OUT / "banner", slug, widths, d.get("quality", 82),
                      upscale_from=cropped.size[0])
        print(f"  {slug:<22} from {spec['source']:<24} crop {cropped.size[0]}x{cropped.size[1]}")
        if spec.get("note"):
            notes.append(f"{slug}: {' '.join(spec['note'].split())}")


def _hex_rgba(value: str) -> tuple:
    """#RRGGBB -> (r, g, b, 255)."""
    v = value.lstrip("#")
    return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16), 255)


def background_alpha(img: Image.Image, threshold: int) -> Image.Image:
    """Alpha mask that removes the flat background surrounding a logo.

    Keys out near-white pixels ONLY where they connect to the image border, so a
    logo's light interior tones survive. A plain "everything near white becomes
    transparent" rule bleached the pale gold in the ICREA mark.

    Existing transparency in the source is respected. Falls back to a corner
    flood-fill if SciPy is unavailable.
    """
    rgba = img.convert("RGBA")
    w, h = rgba.size

    # Respect real transparency if the source already has it.
    alpha = rgba.split()[-1]
    if alpha.getextrema()[0] < 250:
        return alpha

    flat = Image.new("RGB", rgba.size, (255, 255, 255))
    flat.paste(rgba, (0, 0), rgba)

    try:
        import numpy as np
        from scipy import ndimage
    except ImportError:
        # Pure-Pillow fallback: flood from each corner with a sentinel colour.
        from PIL import ImageDraw
        sentinel = (255, 0, 255)
        probe = flat.copy()
        for corner in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
            if min(probe.getpixel(corner)) >= threshold:
                ImageDraw.floodfill(probe, corner, sentinel,
                                    thresh=255 - threshold)
        arr = probe.load()
        mask = Image.new("L", rgba.size, 255)
        mpx = mask.load()
        for y in range(h):
            for x in range(w):
                if arr[x, y] == sentinel:
                    mpx[x, y] = 0
        return mask

    a = np.asarray(flat, dtype=np.uint8)
    near_white = (a >= threshold).all(axis=2)
    # 4-connectivity: diagonal leaks would eat through thin strokes.
    labels, count = ndimage.label(near_white)
    if count == 0:
        return Image.new("L", rgba.size, 255)
    border = np.concatenate([
        labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1],
    ])
    background_ids = np.unique(border[border > 0])
    is_background = np.isin(labels, background_ids)
    return Image.fromarray(np.where(is_background, 0, 255).astype(np.uint8), "L")


def build_logos() -> None:
    print("Logos")
    for slug, spec in CFG.get("logos", {}).items():
        try:
            img = load_source("logos", spec["source"])
        except FileNotFoundError as exc:
            warnings.append(f"{slug}: original missing ({exc}) — no image generated.")
            print(f"  {slug:<22} MISSING SOURCE")
            continue

        # Institutional marks are never recoloured or redrawn. The only edits are
        # removing the flat background and matching optical height, so the three
        # sit on one baseline without any of them visually dominating.
        threshold = int(spec.get("white_threshold", 240))
        rgba = img.convert("RGBA")
        rgba.putalpha(background_alpha(img, threshold))

        # Trim to the real mark using the keyed alpha, so the three logos are
        # sized by their content rather than by whatever padding each file has.
        bbox = rgba.split()[-1].getbbox()
        if bbox:
            rgba = rgba.crop(bbox)

        bg = CFG["defaults"].get("logo_background")
        if bg:
            # Flatten onto the page colour. Keeping the alpha would leave the
            # mark altered wherever a light element connects to the background.
            flat = Image.new("RGBA", rgba.size, _hex_rgba(bg))
            flat.alpha_composite(rgba)
            rgba = flat

        target_h = int(spec["optical_height"])
        out_dir = OUT / "logos"
        out_dir.mkdir(parents=True, exist_ok=True)
        for scale, suffix in ((1, ""), (2, "@2x")):
            hh = target_h * scale
            ww = max(1, round(rgba.size[0] * hh / rgba.size[1]))
            rgba.resize((ww, hh), LANCZOS).save(
                out_dir / f"{slug}{suffix}.png", "PNG", optimize=True)
        print(f"  {slug:<22} from {spec['source']:<24} "
              f"content {rgba.size[0]}x{rgba.size[1]} -> {target_h}px tall")
        if rgba.size[1] < target_h * 2:
            warnings.append(
                f"{slug}: source is {rgba.size[1]}px tall but the 2x version needs "
                f"{target_h * 2}px — it is upscaled. A vector (SVG/EPS) or larger "
                f"raster from the institution would be sharper."
            )


def write_logo_include() -> None:
    """Write _logos.md — the institutional logo row, generated from images.yml.

    The home page includes this rather than hardcoding the logos, so alt text,
    links and sizes stay in the data file.
    """
    # Raw HTML block, not a fenced div: Pandoc wraps the contents of a fenced
    # div in a <p>, which leaves the flex container with a single child and
    # silently discards the gap between the logos.
    lines = [
        "<!-- GENERATED by scripts/build_images.py from data/images.yml.",
        "     Hand edits will be overwritten. -->",
        "```{=html}",
        '<div class="cbc-logos">',
    ]
    for slug, spec in CFG.get("logos", {}).items():
        h = int(spec["optical_height"])
        img = (f'<img src="assets/images/logos/{slug}.png" '
               f'srcset="assets/images/logos/{slug}.png 1x, '
               f'assets/images/logos/{slug}@2x.png 2x" '
               f'height="{h}" alt="{spec["alt"]}">')
        url = spec.get("url")
        lines.append(f'<a href="{url}">{img}</a>' if url else img)
    lines.append("</div>")
    lines.append("```")
    out = ROOT / "_logos.md"
    out.write_text("\n".join(lines) + "\n")
    print(f"  {out.relative_to(ROOT)}")
    # Quarto's incremental render does not treat an include as a dependency, so
    # the page that includes this file would otherwise keep its old content.
    for name in ("index.qmd", "contact.qmd"):
        page = ROOT / name
        if page.exists():
            page.touch()


def main() -> None:
    global CFG
    if not CONFIG.exists():
        sys.exit(f"Missing config: {CONFIG.relative_to(ROOT)}")
    CFG = yaml.safe_load(CONFIG.read_text())
    warn_if_preview_running(warnings)
    print(f"Treatment: {CFG['defaults'].get('treatment')}\n")
    build_people()
    print()
    build_banner()
    print()
    build_logos()
    print()
    print("Includes")
    write_logo_include()

    if notes:
        print("\nNotes carried from data/images.yml:")
        for n in notes:
            print(f"  - {n}")
    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"  ! {w}")
    print("\nDone. Generated files are committed; the originals in "
          "assets/images/_originals/ are the source of truth.")


if __name__ == "__main__":
    main()

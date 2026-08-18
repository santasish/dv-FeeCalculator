"""Regenerates assets/social-preview.png (GitHub social card, 1280x640).

Run from the repo root:  python assets/make_social_preview.py

Kept in the repo so the card can be re-issued whenever the tagline changes,
instead of being re-drawn by hand. Same composition as the original: navy
field, centred lockup, the gold rule the app header uses, title, tagline.
Segoe UI is used because it is what the app renders in on Windows; the
script falls back to Pillow's default font elsewhere, which will look worse
-- regenerate on a machine with Segoe UI.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
W, H = 1280, 640
NAVY = "#0A1424"
GOLD = "#CBA135"
WHITE = "#FFFFFF"
MUTED = "#B7BDC7"

TITLE = ["Fund Management", "Service Charge Calculator"]
TAGLINE = "Hurdle-rate fee modelling  ·  5-year projection  ·  CLTV  ·  Charts"


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    for candidate in (Path("C:/Windows/Fonts") / name, HERE / name):
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default(size)


def main() -> None:
    card = Image.new("RGB", (W, H), NAVY)
    draw = ImageDraw.Draw(card)

    # Lockup: the transparent logo, scaled to ~320px wide, centred at y=190.
    logo = Image.open(HERE / "datavynx-logo-transparent.png").convert("RGBA")
    # The asset carries transparent margins; crop to the artwork so the
    # target width applies to the visible lockup.
    logo = logo.crop(logo.getbbox())
    logo_w = 320
    logo = logo.resize((logo_w, int(logo.height * logo_w / logo.width)), Image.LANCZOS)
    card.paste(logo, ((W - logo.width) // 2, 190 - logo.height // 2), logo)

    # Gold rule -- the "structure" cue from the app's title bar.
    draw.rectangle([(W // 2 - 90, 328), (W // 2 + 90, 333)], fill=GOLD)

    title_font = font("segoeuib.ttf", 54)
    y = 385
    for line in TITLE:
        w = draw.textlength(line, font=title_font)
        draw.text(((W - w) / 2, y), line, font=title_font, fill=WHITE)
        y += 64

    tag_font = font("segoeui.ttf", 28)
    w = draw.textlength(TAGLINE, font=tag_font)
    draw.text(((W - w) / 2, 520), TAGLINE, font=tag_font, fill=MUTED)

    card.save(HERE / "social-preview.png", optimize=True)


if __name__ == "__main__":
    main()

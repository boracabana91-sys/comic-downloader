"""One picture with every cutout, labelled, so they can be checked by eye:  python contact_sheet.py PLAYERS_DIR OUT.jpg"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont


def main(root: str, out: str, cols: int = 6, cell=(300, 380)) -> None:
    names = sorted(n for n in os.listdir(root) if os.path.exists(os.path.join(root, n, "cutout.png")))
    rows = (len(names) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell[0], max(1, rows) * cell[1]), (52, 56, 66))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    for i, n in enumerate(names):
        im = Image.open(os.path.join(root, n, "cutout.png")).convert("RGBA")
        k = min((cell[0] - 16) / im.width, (cell[1] - 44) / im.height)
        im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))))
        x, y = (i % cols) * cell[0], (i // cols) * cell[1]
        sheet.paste(im, (x + (cell[0] - im.width) // 2, y + cell[1] - 40 - im.height), im)
        d.text((x + 8, y + cell[1] - 34), n.split(" - ", 1)[1], fill=(255, 255, 255), font=font)
    sheet.save(out, quality=88)
    print(f"{len(names)} cutouts -> {out}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

"""Contact sheets of the candidate cut-outs, to pick by eye:  python cands_sheet.py PLAYERS_DIR OUT_PREFIX
One sheet per 6 teams; every player is a row, candidates are numbered 1..N (1 = the one the fetch chose)."""
import os
import sys

from PIL import Image, ImageDraw, ImageFont


def main(root, prefix, per=10, n=8, cell=(210, 300)):
    base = os.path.join(root, "_cands")
    names = sorted(os.listdir(base))
    font = ImageFont.truetype("DejaVuSans-Bold.ttf", 15)
    for s in range(0, len(names), per):
        chunk = names[s:s + per]
        sheet = Image.new("RGB", (n * cell[0] + 220, len(chunk) * cell[1]), (52, 56, 66))
        d = ImageDraw.Draw(sheet)
        for r, name in enumerate(chunk):
            d.text((8, r * cell[1] + 8), name.split(" - ", 1)[1], fill=(255, 255, 0), font=font)
            status = {}
            idx = os.path.join(base, name, "index.txt")
            if os.path.exists(idx):                       # vv13: "n<TAB>title<TAB>current|other|unknown"
                for line in open(idx, encoding="utf-8"):
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) >= 3:
                        status[parts[0]] = parts[2]
            for k in range(1, n + 1):
                f = os.path.join(base, name, f"{k}.png")
                if not os.path.exists(f):
                    continue
                im = Image.open(f).convert("RGBA")
                m = min((cell[0] - 10) / im.width, (cell[1] - 26) / im.height)
                im = im.resize((max(1, int(im.width * m)), max(1, int(im.height * m))))
                x, y = 220 + (k - 1) * cell[0], r * cell[1]
                sheet.paste(im, (x + 5, y + cell[1] - im.height - 2), im)
                st = status.get(str(k), "")
                tag, col = {"current": ("NOW", (90, 255, 120)), "other": ("OLD", (255, 110, 110))}.get(st, ("", (255, 255, 255)))
                d.text((x + 6, y + 4), f"{k} {tag}", fill=col, font=font)
        out = f"{prefix}{s // per + 1}.jpg"
        sheet.save(out, quality=85)
        print(out, len(chunk))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

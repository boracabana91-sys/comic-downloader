"""Makes a fake broadcast used by the self-check and the tests (no real footage needed)."""
import subprocess

from . import media


def make_video(path, secs=60, w=1280, h=720, live="between(t,0,20)+between(t,30,50)"):
    """The 'clock' digits flip every second while live (0-20s, 30-50s) and freeze otherwise."""
    x, y = int(w * 0.475), int(h * 0.828)
    a = f"drawbox=x={x+4}:y={y+4}:w=20:h=14:color=white:t=fill:enable='(lt(mod(t,2),1)*({live}))+(1-({live}))'"
    b = f"drawbox=x={x+36}:y={y+16}:w=20:h=14:color=white:t=fill:enable='gte(mod(t,2),1)*({live})'"
    subprocess.run([media.need("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"color=c=0x101010:s={w}x{h}:r=30:d={secs}", "-f", "lavfi", "-i", f"sine=f=440:d={secs}",
                    "-vf", f"{a},{b}", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", path],
                   check=True)

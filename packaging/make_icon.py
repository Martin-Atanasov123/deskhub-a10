"""Draw packaging/deskhub.ico: the same little desk display the tray shows, in amber on a dark tile."""
import io
import pathlib
import sys

from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "companion"))
from deskhub.tray import AMBER, icon_png  # noqa: E402

base = Image.open(io.BytesIO(icon_png(AMBER, 256))).convert("RGBA")
tile = Image.new("RGBA", (256, 256), (11, 15, 16, 255))
tile.alpha_composite(base)
out = pathlib.Path(__file__).resolve().parent / "deskhub.ico"
tile.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("wrote", out)

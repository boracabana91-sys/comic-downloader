"""Self-test: serves a fake chapter page locally and checks the 5-page folder grouping."""
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import core

N = 12
PAGE = """<html><head><title>My Comic - Chapter 7 - Lua Comic</title></head><body>
<img src="/static/logo.png">
%s
<img src="/ads/promo.jpg">
<img src="/thumbs/other1.jpg"><img src="/thumbs/other2.jpg">
<script>var x = {"p": ["%s"]};</script>
</body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/chapter":
            tags = "".join(f'<img data-src="/img/{i:02d}.webp" src="data:image/gif;base64,AAAA">'
                           for i in range(1, 10))
            extra = '","'.join(f"http:\\/\\/127.0.0.1:{self.server.server_port}\\/img\\/{i:02d}.webp"
                               for i in range(10, N + 1))
            body = (PAGE % (tags, extra)).encode()
        elif self.path.startswith("/img/"):
            body = os.urandom(500)
        else:
            body = b"x" * 300
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)


def main():
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/chapter"
    info = core.inspect_page(url)
    assert info["title"] == "My Comic - Chapter 7", info["title"]
    assert len(info["images"]) == N, (len(info["images"]), info["images"])
    with tempfile.TemporaryDirectory() as d:
        failed = core.download_images(info["images"], info["title"], d, url)
        assert failed == [], failed
        folders = sorted(os.listdir(d))
        assert folders == ["My Comic - Chapter 7 - Pages 1-5",
                           "My Comic - Chapter 7 - Pages 11-12",
                           "My Comic - Chapter 7 - Pages 6-10"], folders
        assert sorted(os.listdir(os.path.join(d, folders[2]))) == [
            "006.webp", "007.webp", "008.webp", "009.webp", "010.webp"]
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()

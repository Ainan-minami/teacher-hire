"""本地预览前端（无需任何依赖）：

    python scripts/serve.py 8000

然后浏览器打开 http://localhost:8000
"""

import functools
import http.server
import os
import sys

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000

handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=WEB_DIR)
with http.server.ThreadingHTTPServer(("0.0.0.0", PORT), handler) as srv:
    print(f"教师招聘聚合站本地预览: http://localhost:{PORT}")
    print(f"数据目录: {WEB_DIR}")
    srv.serve_forever()

"""Dev-server entrypoint — used by the local Docker Compose stack's Dockerfile
CMD (`python -u src/server.py`), which is how /root/claude/dscoaching's own
docker-compose.yml boots the `dscoach-app` container. Not used for the
ecb.pm production container — that runs server_docker.py instead (this file
predates the Docker split and originally targeted Wasmer Edge, hence the
dual-layout sys.path handling below).
"""

import os
import sys

# Support both Wasmer (/lib, /src) and Docker (/app/lib, /app/src) layouts
for p in ["/app/lib", "/app/src", "/lib", "/src"]:
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

from app import app  # noqa: E402 - must follow the sys.path setup above

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 80))
    app.run(host="0.0.0.0", port=port, use_reloader=False)  # nosec B104 - required for container

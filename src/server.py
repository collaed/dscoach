import os
import sys

# Support both Docker (/app/lib, /app/src) and local (/lib, /src) layouts
for p in ["/app/lib", "/app/src", "/lib", "/src"]:
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

from app import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 80))
    app.run(host="0.0.0.0", port=port, use_reloader=False)  # nosec B104 - required for container

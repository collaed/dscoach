"""Production entrypoint — this is what the `coaching` container on ecb.pm
actually runs (CMD in /opt/apps/coaching's Dockerfile), listening on
PORT=8000 behind the Caddy reverse proxy at dscoaching.ecb.pm. Simpler than
server.py (no Wasmer-era dual-path handling) since the Docker layout is
fixed and known.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from app import app

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8000)), use_reloader=False)

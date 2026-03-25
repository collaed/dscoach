import sys
import os
sys.path.insert(0, '/lib')
sys.path.insert(0, '/src')

from app import app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 80))
    app.run(host='0.0.0.0', port=port, use_reloader=False)

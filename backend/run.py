import os
from pathlib import Path
from dotenv import load_dotenv
import uvicorn

root = Path(__file__).resolve().parent.parent
load_dotenv(root / '.env')
if __name__ == '__main__':
    socket = os.environ.get('BACKEND_SOCKET')
    if socket:
        # The socket is private to the service user, not an externally exposed API port.
        os.umask(0o077)
        uvicorn.run('server:app', uds=socket, proxy_headers=False, access_log=False, log_level='info')
    else:
        host = os.environ.get('BACKEND_HOST', '127.0.0.1')
        port = int(os.environ.get('BACKEND_PORT', '8000'))
        uvicorn.run('server:app', host=host, port=port, proxy_headers=False, access_log=False, log_level='info')

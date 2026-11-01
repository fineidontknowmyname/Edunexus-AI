import os
import sys
import subprocess
from urllib.parse import urlsplit, urlunsplit

with open('backend/.env') as f:
    for line in f:
        if line.startswith('DATABASE_URL='):
            db_url = line.strip().split('=', 1)[1].strip('"\'')
            break

parts = urlsplit(db_url)
test_url = urlunsplit((parts.scheme, parts.netloc, '/edunexus_test_p3b4', parts.query, parts.fragment))
env = os.environ.copy()
env['DATABASE_URL'] = test_url
env['EDUNEXUS_DB_TESTS'] = '1'

py_exe = os.path.abspath(r'backend\.venv\Scripts\python.exe')
args = sys.argv[1:] if len(sys.argv) > 1 else ['backend/tests/test_safety_guard.py']
res = subprocess.run([py_exe, '-m', 'pytest'] + args, env=env, capture_output=True, text=True)
print(res.stdout)
if res.stderr:
    print('STDERR:', res.stderr)
sys.exit(res.returncode)

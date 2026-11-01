import json
import os
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from dotenv import dotenv_values

cfg = dotenv_values('backend/.env')
db_url = cfg.get('DATABASE_URL')
parts = urlsplit(db_url)
test_url = urlunsplit((parts.scheme, parts.netloc, '/edunexus_test_p3b4', parts.query, parts.fragment))

env = os.environ.copy()
env['DATABASE_URL'] = test_url
env['EDUNEXUS_DB_TESTS'] = '1'

py_exe = os.path.abspath(r'backend\.venv\Scripts\python.exe')

test_files = sorted(Path('backend/tests').glob('test_*.py'))
print(f"Discovered {len(test_files)} test files to execute.")

results = []

for tf in test_files:
    fname = tf.name
    print(f"Running {fname}...", flush=True)
    t0 = time.time()
    try:
        res = subprocess.run(
            [py_exe, '-m', 'pytest', str(tf), '-v'],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        duration = round(time.time() - t0, 2)
        out = res.stdout + "\n" + res.stderr
        
        # Parse pytest output
        passed = 0
        failed = 0
        skipped = 0
        errored = 0
        
        # summary line like: "=== 9 passed, 1 failed, 2 skipped, 1 error in 4.5s ==="
        m_pass = re.search(r'(\d+)\s+passed', out)
        m_fail = re.search(r'(\d+)\s+failed', out)
        m_skip = re.search(r'(\d+)\s+skipped', out)
        m_err = re.search(r'(\d+)\s+error', out)
        
        if m_pass: passed = int(m_pass.group(1))
        if m_fail: failed = int(m_fail.group(1))
        if m_skip: skipped = int(m_skip.group(1))
        if m_err: errored = int(m_err.group(1))
        
        # Collect failure lines
        reasons = []
        for line in out.splitlines():
            if line.startswith("FAILED ") or line.startswith("ERROR "):
                reasons.append(line.split()[1] if len(line.split()) > 1 else line)
        
        results.append({
            "file": fname,
            "status": "PASS" if res.returncode == 0 else "FAIL",
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "errored": errored,
            "duration": duration,
            "returncode": res.returncode,
            "reasons": "; ".join(reasons[:5]),
            "timed_out": False
        })
        print(f"  -> {results[-1]['status']} (passed={passed}, failed={failed}, errored={errored}) in {duration}s")
    except subprocess.TimeoutExpired:
        duration = round(time.time() - t0, 2)
        print(f"  -> TIMEOUT after {duration}s")
        results.append({
            "file": fname,
            "status": "TIMEOUT",
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "errored": 1,
            "duration": duration,
            "returncode": -1,
            "reasons": "Execution timed out (> 120s)",
            "timed_out": True
        })

with open('baseline_results_p3c.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, indent=2)

print("\nSaved baseline_results_p3c.json!")

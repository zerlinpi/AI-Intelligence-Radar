import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "send_chatgpt_feed.py"


def test_chatgpt_feed_script_can_import_app_when_run_as_file():
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["GITHUB_REPOSITORY"] = ""
    env["GITHUB_TOKEN"] = ""

    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    # The script is expected to stop at its explicit runtime preflight because
    # credentials are intentionally blank. It must get past `from app...`
    # imports when executed exactly the same way GitHub Actions executes it.
    assert result.returncode != 0
    combined = f"{result.stdout}\n{result.stderr}"
    assert "ModuleNotFoundError" not in combined
    assert "缺少 GITHUB_REPOSITORY" in combined

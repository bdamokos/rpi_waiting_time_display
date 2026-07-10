import os
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "docs/service/limit_log_size.sh"


def test_log_guard_preserves_tail_and_truncates_oversized_file(tmp_path):
    log = tmp_path / "display.err"
    content = bytes(range(200))
    log.write_bytes(content)
    environment = os.environ | {
        "DISPLAY_LOG_MAX_BYTES": "100",
        "DISPLAY_LOG_KEEP_BYTES": "20",
    }

    subprocess.run([SCRIPT, log], check=True, env=environment)

    assert log.read_bytes() == b""
    assert log.with_suffix(".err.previous").read_bytes() == content[-20:]


def test_log_guard_leaves_small_file_untouched(tmp_path):
    log = tmp_path / "display.out"
    log.write_text("small", encoding="utf-8")
    environment = os.environ | {"DISPLAY_LOG_MAX_BYTES": "100"}

    subprocess.run([SCRIPT, log], check=True, env=environment)

    assert log.read_text(encoding="utf-8") == "small"
    assert not log.with_suffix(".out.previous").exists()

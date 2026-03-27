import os
import signal
import subprocess
import time

from engine.binary_resolver import describe_scrcpy_resolution, scrcpy_install_hint

SCRCPY_MAX_FPS = os.environ.get("SCRCPY_MAX_FPS", "60")
SCRCPY_STARTUP_WAIT = float(os.environ.get("SCRCPY_STARTUP_WAIT", "1.0"))


def resolve_scrcpy_bin():
    resolved, _source = describe_scrcpy_resolution()
    if resolved:
        return resolved

    raise FileNotFoundError(
        "scrcpy executable not found. Checked SCRCPY_BIN, bundled `third_party/scrcpy`, "
        f"and PATH. {scrcpy_install_hint()}"
    )


def start_record(video_path, serial=None):
    os.makedirs(os.path.dirname(video_path) or ".", exist_ok=True)
    scrcpy_bin = resolve_scrcpy_bin()
    cmd = [
        scrcpy_bin,
        "--record",
        video_path,
        "--no-playback",
        "--max-fps",
        str(SCRCPY_MAX_FPS),
        "--no-audio",
        "--no-window",
    ]
    if serial:
        cmd.extend(["--serial", str(serial)])
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["preexec_fn"] = os.setsid
    proc = subprocess.Popen(cmd, **kwargs)
    time.sleep(SCRCPY_STARTUP_WAIT)
    return proc


def stop_record(proc):
    if proc.poll() is not None:
        return

    try:
        if os.name == "nt":
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(proc.pid, signal.SIGINT)
    except OSError:
        proc.terminate()

    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()

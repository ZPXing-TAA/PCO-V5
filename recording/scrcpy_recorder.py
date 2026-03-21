import os
import signal
import shutil
import subprocess
import time

SCRCPY_MAX_FPS = os.environ.get("SCRCPY_MAX_FPS", "60")
SCRCPY_STARTUP_WAIT = float(os.environ.get("SCRCPY_STARTUP_WAIT", "1.0"))
WINDOWS_SCRCPY_FALLBACK = r"D:/Softwares/scrcpy-win64-v3.3.3/scrcpy.exe"


def resolve_scrcpy_bin():
    env_value = os.environ.get("SCRCPY_BIN")
    if env_value:
        return env_value

    discovered = shutil.which("scrcpy")
    if discovered:
        return discovered

    if os.name == "nt" and os.path.exists(WINDOWS_SCRCPY_FALLBACK):
        return WINDOWS_SCRCPY_FALLBACK

    if os.name == "nt":
        raise FileNotFoundError(
            "scrcpy executable not found. Install scrcpy or set SCRCPY_BIN, "
            f"for example: {WINDOWS_SCRCPY_FALLBACK}"
        )

    raise FileNotFoundError(
        "scrcpy executable not found. Install scrcpy or set SCRCPY_BIN, "
        "for example: /opt/homebrew/bin/scrcpy"
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

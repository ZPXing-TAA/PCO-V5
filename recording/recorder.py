from recording.scrcpy_recorder import start_record, stop_record

class Recorder:
    def __init__(self, video_path, serial=None):
        self.video_path = video_path
        self.serial = serial
        self.proc = None

    def start(self):
        if self.proc is None:
            print(f"[RECORD] 开始录制 {self.video_path}")
            self.proc = start_record(self.video_path, serial=self.serial)

    def stop(self):
        if self.proc is not None:
            print("[RECORD] 停止录制")
            stop_record(self.proc)
            self.proc = None

# Bundled Third-Party Tools

This project can use bundled copies of `adb`, `scrcpy`, `ffmpeg`, and `ffprobe` so a fresh machine does not need a global install first.

Resolution order:

1. Explicit env var
2. Bundled binary under `third_party/...`
3. System `PATH`

## Supported layout

```text
third_party/
  platform-tools/
    windows/
      platform-tools/
        adb.exe
    macos/
      platform-tools/
        adb
    linux/
      platform-tools/
        adb
  scrcpy/
    windows/
      scrcpy-win64-v3.x/
        scrcpy.exe
        adb.exe
        SDL2.dll
        ...
    macos/
      scrcpy-macos-.../
        scrcpy
        ...
    linux/
      scrcpy-linux-.../
        scrcpy
        ...
  ffmpeg/
    windows/
      ffmpeg-master-latest-win64-gpl/
        bin/
          ffmpeg.exe
          ffprobe.exe
    macos/
      ffmpeg-.../
        bin/
          ffmpeg
          ffprobe
    linux/
      ffmpeg-.../
        bin/
          ffmpeg
          ffprobe
```

The resolver searches recursively inside the platform folder, so the extracted official release directory name does not need to be renamed.

The repository already includes visible `windows/` placeholder folders under both `platform-tools/` and `scrcpy/`
so the intended layout is obvious on a fresh checkout.

For `adb`, the project first prefers `third_party/platform-tools/<platform>/...`, but it can also reuse `adb.exe` found inside the Windows scrcpy release.

## Environment variables

- `ADB_BIN`: absolute path to `adb` if you want to override everything
- `SCRCPY_BIN`: absolute path to `scrcpy` if you want to override everything
- `FFMPEG_BIN`: absolute path to `ffmpeg` if you want to override everything
- `FFPROBE_BIN`: absolute path to `ffprobe` if you want to override everything

## Recommended source

Only use the official releases:

- `adb`: Android SDK Platform Tools from Google
- `scrcpy`: [Genymobile/scrcpy](https://github.com/Genymobile/scrcpy)
- `ffmpeg`: official builds from [ffmpeg.org](https://ffmpeg.org/download.html) or a trusted official mirror linked there

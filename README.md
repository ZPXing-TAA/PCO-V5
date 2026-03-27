# Auto_Scripts_v5

`Auto_Scripts_v5` is a fresh shared-runner implementation. `Auto_Scripts_v4` remains reference-only.

## Primary Entry Points

- `multiroute.py`
- `debug_multiroute.py`
- `test_route.py`

New devices should use runtime ADB discovery plus optional `device_profiles/<device_id>.json`.
Do not add new per-device `multiroute_*`, `debug_multi_route_*`, or `test_*` scripts here.

These shared entry scripts are intended for local, supervised use.
The main control surface is the editable constants at the top of each script, matching the v4 workflow style more closely than a CLI-heavy service-style interface.
Device-bound values are not meant to be edited there:

- `serial` auto-discovers from ADB
- `device_id` auto-derives from discovered metadata, then matches optional profile data
- `target_resolution` comes from discovery, with optional profile override
- `video_base` falls back to `recordings/<device_id>` when no profile default exists
- `config_root` defaults to `Auto_Scripts_v5/render_configs`
- `route_subpath` defaults to `natlan`, resolved under `routes/`

## Runtime Model

Runtime uses the following naming consistently:

- `serial`: current ADB connection target only
- `device_label`: human-readable name for logs
- `device_id`: canonical persisted profile identity
- `discovered_device`: raw metadata from ADB
- `device_profile`: optional JSON data file
- `runtime_device_context`: final merged runtime object

Merge order:

1. `discovered_device`
2. matching `device_profile`
3. explicit env / code overrides

## Shared Scaling Rule

- Baseline coordinates are `HUAWEI Pura 70` landscape `2848x1276`.
- Route `PORTAL` / `NEXT_PORTAL`, action points, and render-config taps/swipes all scale from the same baseline source.
- No rotation logic is used in the primary path.

## Profiles

Profiles live under `device_profiles/<device_id>.json`.

Example fields:

- `target_resolution`
- `offsets`
- `defaults.video_base`
- `defaults.config_root`
- `legacy_aliases`

If no profile matches, the runner still proceeds with:

- discovered `serial`
- discovered `manufacturer`
- discovered `model`
- discovered `resolution`
- empty `offsets`

## Usage

Single connected device:

```bash
python3 multiroute.py
```

For the fixed 12-config power-measurement pass on one route:

```bash
python3 measure_12_key_configs.py
```

This uses the fixed order from `measure_12_key_configs.md`, runs only one `ROUTE_SUFFIX`, skips
all `record_start` / `record_stop` actions, and does not transition to the next route after the
last config.

For frequent local adjustments, edit the constants directly inside:

- `multiroute.py`
- `measure_12_key_configs.py`
- `debug_multiroute.py`
- `test_route.py`

Those constants should stay focused on local workflow control:

- route windows and skip lists
- restart windows
- test mode
- step timing

Env controls are still available when convenient:

- `ADB_BIN`
- `AUTO_SERIAL`
- `AUTO_DEVICE_ID`
- `AUTO_TARGET_RESOLUTION`
- `AUTO_CONFIG_ROOT`
- `AUTO_VIDEO_BASE`
- `AUTO_SKIP_ROUTE_SUFFIXES`
- `AUTO_TOTAL_CONFIGS_PER_ROUTE`
- `AUTO_ROUTE_SUFFIX`
- `AUTO_TEST_MODE`
- `AUTO_SKIP_TELEPORT`
- `SCRCPY_BIN`
- `SCRCPY_MAX_FPS`
- `SCRCPY_STARTUP_WAIT`

## Tool Resolution

`adb` lookup order:

1. `ADB_BIN`
2. bundled binary under `third_party/platform-tools/<platform>/...`
3. bundled `adb` under `third_party/scrcpy/<platform>/...` when present
4. system `PATH`

`scrcpy` lookup order:

1. `SCRCPY_BIN`
2. bundled binary under `third_party/scrcpy/<platform>/...`
3. system `PATH`

This means a fresh machine can work without global installs if you extract the official Android Platform Tools package into `third_party/platform-tools/<platform>/` and the official scrcpy release into `third_party/scrcpy/<platform>/`.

On Windows, the official `scrcpy` release already contains `adb.exe`, so extracting only the scrcpy zip is often enough for this project.

Recommended platform folder names:

- `windows`
- `macos`
- `linux`

Official sources:

- `adb`: Android SDK Platform Tools
- `scrcpy`: [Genymobile/scrcpy](https://github.com/Genymobile/scrcpy)

Install fallback if you prefer global tools:

- macOS: `brew install scrcpy` and `brew install --cask android-platform-tools`
- Windows: `winget install --exact Genymobile.scrcpy`
- Linux: install `adb` and `scrcpy` from your package manager or use the official releases

## Small Tool

On a fresh machine, run `tools/check_tools.py` first to verify where `adb` and `scrcpy` are being resolved from.

To map coordinates measured on another device back to the shared baseline route space:

1. Open `tools/map_to_baseline.py`
2. Keep one adb device connected
3. Edit `POINTS`
4. Run the file in IDE
5. If multiple devices are connected, set `SERIAL`

To open scrcpy with Android `pointer_location` enabled for manual coordinate pickup:

1. Open `tools/get_coordinate.py`
2. Keep one adb device connected
3. If multiple devices are connected, set `SERIAL`
4. Run the file in IDE
5. Close scrcpy when finished; the script restores `pointer_location` automatically

To dry-run a v5 recording-directory rename into the current `natlan_rXX_<label><nn>` format:

```bash
python3 tools/rename_recordings.py
```

Add `--apply` only after checking the printed plan.

## Spec Conflict Note

Project root still contains legacy device-specific render-config directories such as:

- `render_configs_huaweimate`
- `render_configs_ofx`

These are already materialized per-device coordinate copies, which conflicts with the v5 spec requirement that render-config scaling come from the same baseline source as portal and action scaling.

Minimal deviation chosen in v5:

- primary shared path defaults to baseline `render_configs`
- legacy per-device render-config folders are not auto-selected by the shared runner
- if a future device truly needs a non-baseline source, that should be treated as an explicit override rather than the default shared path

`skip_route_suffixes` is now treated as shared runner control instead of device-bound profile data.

- no shared default skip list is imposed
- skip lists are supplied from the shared entry script constants or env
- profile `defaults.skip_route_suffixes` is ignored if present in legacy data

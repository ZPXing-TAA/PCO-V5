# iOS Backend Spec

## 目标

新开一个独立的 iOS backend 项目，不复用当前工程里的 Android 执行链路，只复用这两层：

1. `route` 数据模型
2. 坐标缩放模型

不复用的部分：

- `adb`
- `scrcpy`
- Android 设备发现
- Android 输入注入
- Android 录屏实现

## 为什么要单独起 iOS Backend

当前工程的执行后端是 Android 专用：

- 设备发现依赖 `adb devices`、`adb shell getprop`、`adb shell wm size`
- 输入注入依赖 `adb shell input tap/swipe`
- 录屏依赖 `scrcpy --record`

这些都不能直接搬到 iPhone 真机。

因此正确做法不是在现有 backend 上硬补 iOS 分支，而是把“route/坐标模型”抽成共享层，然后为 iOS 单独实现一套 runtime adapter。

## 推荐技术路线

推荐 iOS backend 以 `Appium XCUITest Driver` 作为主执行后端。

原因：

- Appium 官方把 `XCUITest` 作为 iOS 的主支持方案
- Appium 的 iOS 控制底层通过 `WebDriverAgent` 完成
- Appium 已经提供了坐标 tap、drag/swipe、screen recording 等能力
- 比直接自己维护一套 WDA 链路更稳

不建议直接把 archived 的原始 `WebDriverAgent` 当主入口。

原因：

- Facebook 原始 `WebDriverAgent` 仓库已归档
- Appium 仍在基于其生态做维护和封装
- 真机签名、启动、端口转发、会话管理都已经是 Appium/XCUITest 的成熟路径

## 关键设计决策

### 1. 共享 route 语义，不共享 backend 实现

新项目里继续沿用现有 route 结构：

```python
ROUTE = [
    ("record_start",),
    ("run", 10),
    ("record_stop",),
    ("teleport",),
]

PORTAL = [1500, 650]
NEXT_PORTAL = [1130, 835]
```

也继续沿用现有动作语义集合，例如：

- `move`
- `run`
- `climb`
- `glide`
- `turn_right_90`
- `turn_left_90`
- `teleport`
- `record_start`
- `record_stop`

但是这些动作在 iOS 中的执行方式必须全部重新实现。

### 2. 保留统一 baseline 坐标系

为兼容当前 route 资产，建议继续保留现有 baseline：

- baseline device: `HUAWEI Pura 70`
- baseline resolution: `2848x1276`

这样现有 route 文件可以直接复用，不需要批量改坐标源。

### 3. iOS 不要直接用“物理分辨率”做点击目标

这是 iOS backend 最容易踩坑的点。

Appium XCUITest 的坐标手势文档说明，`mobile: tap` 的 `x/y` 是相对于当前 active application 计算的，而不是明确承诺等于设备面板物理像素。基于这一点，我建议：

- Android 旧模型里的 baseline 仍然保存为 `2848x1276`
- iOS runtime 的 `target_resolution` 不要直接取 iPhone 面板分辨率
- iOS runtime 应优先取“当前 app viewport / window rect”的宽高作为目标坐标空间

这是根据 Appium 坐标定义做出的工程推断，目的是避免 Retina scale、safe area、系统栏导致的偏移。

换句话说：

- route 文件里仍然保存 baseline 坐标
- iOS 执行前，先拿到当前 app 的有效坐标空间
- 再把 baseline 坐标映射到 iOS viewport 坐标

## 坐标模型

### 输入

- baseline 点位：`[x_base, y_base]`
- baseline resolution：`2848x1276`
- iOS viewport size：`(viewport_w, viewport_h)`
- 可选 profile offsets

### 输出

- iOS runtime 坐标：`[x_ios, y_ios]`

### 基础换算公式

```text
x_ios = round(x_base * viewport_w / 2848)
y_ios = round(y_base * viewport_h / 1276)
```

### 二级修正

在基础缩放后，允许每台 iPhone profile 再叠加少量 offset：

```text
x_final = x_ios + offset_x
y_final = y_ios + offset_y
```

建议 offset 分层沿用现有思想：

- `GLOBAL`
- `TURN`
- `OPEN_MAP`
- `CONFIRM_TELEPORT`
- 具体动作名

## 推荐项目结构

```text
ios_route_runner/
  README.md
  pyproject.toml
  route_model/
    __init__.py
    scaling.py
    route_types.py
    route_loader.py
  ios_backend/
    __init__.py
    config.py
    device.py
    session.py
    gestures.py
    recorder.py
    actions.py
    runner.py
    profiles.py
  routes/
    natlan/
      1.py
      2.py
      ...
  device_profiles/
    iphone_15_pro_max.json
    iphone_16_pro.json
  tools/
    map_from_ios_to_baseline.py
```

## 模块职责

### `route_model/scaling.py`

只保留纯数学逻辑：

- `BASELINE_RESOLUTION = (2848, 1276)`
- `scale_xy(...)`
- `scale_point(...)`
- `normalize_resolution(...)`

这个模块不依赖 Android，也不依赖 iOS。

### `route_model/route_loader.py`

负责加载 route 文件中的：

- `ROUTE`
- `PORTAL`
- `NEXT_PORTAL`

这一层只处理数据，不接触设备。

### `ios_backend/device.py`

负责设备识别与 viewport 信息：

- 指定或发现目标设备 `udid`
- 建立 Appium session
- 获取当前 app window/viewport rect
- 产出 runtime device context

建议 v1 不做复杂自动发现，只支持：

- 单设备自动选中
- 多设备时手动指定 `UDID`

### `ios_backend/session.py`

负责 Appium session 生命周期：

- 启动 session
- 连接目标 bundle
- 关闭 session
- 会话异常恢复

### `ios_backend/gestures.py`

负责所有底层触控：

- `tap(x, y)`
- `swipe(x1, y1, x2, y2, duration_ms)`
- `long_press(x, y, duration_ms)`

建议优先使用：

- `mobile: tap`
- `mobile: dragFromToForDuration`

复杂手势再退回 W3C actions。

### `ios_backend/recorder.py`

负责录屏：

- `start_recording()`
- `stop_recording()`
- 保存视频到目标路径

推荐优先走 Appium 的 `startRecordingScreen` / `stopRecordingScreen`。

## Runtime Context 设计

建议 iOS runtime context 长这样：

```python
runtime_device_context = {
    "platform": "ios",
    "udid": "...",
    "device_label": "iPhone 15 Pro Max",
    "bundle_id": "...",
    "baseline_resolution": (2848, 1276),
    "viewport_resolution": (viewport_w, viewport_h),
    "offsets": {...},
}
```

重点是：

- iOS 用 `viewport_resolution`
- Android 原模型用 `target_resolution`

这两个概念不要混在一起。

## 动作映射建议

### 可直接复用语义的动作

- `move(seconds)`
- `run(seconds)`
- `climb(seconds)`
- `swim(seconds)`
- `jump()`
- `dash()`
- `attack()`
- `turn_*()`
- `teleport()`
- `record_start`
- `record_stop`

### 需要谨慎验证的动作

- `glide`
- `combat`
- 长按类技能
- 依赖 UI 精准位置的地图点击

这些动作在 iOS 上可能因为：

- 触控采样差异
- 游戏 UI 安全区差异
- 录屏占用资源

导致时序和点击位置都要重调。

## 录屏方案

推荐 v1 直接使用 Appium 提供的录屏能力。

理由：

- iOS 真机已支持 screen recording
- 不需要再单独拼一套屏幕镜像链路
- 和会话生命周期更一致

注意点：

- 需要 `ffmpeg`
- 长时间录制和大文件要单独做落盘策略
- `record_start/record_stop` 的切段逻辑要保留

## MVP 范围

### Phase 1

只做最小闭环：

- 单台 iPhone 真机
- 手动指定 `UDID`
- 启动 Appium session
- 读取 viewport size
- 能执行 `tap/swipe`
- 能跑最简单 route

### Phase 2

补齐录屏：

- `record_start`
- `record_stop`
- 按 route segment 输出视频文件

### Phase 3

补齐地图链路：

- `OPEN_MAP`
- `PORTAL`
- `NEXT_PORTAL`
- `CONFIRM_TELEPORT`
- teleport 成功率验证

### Phase 4

补齐 profile 与偏移：

- iPhone 机型 profile
- offset 调整
- route 稳定性回归

## 明确不做的事

在第一版里，不建议一开始就做这些：

- Android/iOS 双平台统一 runtime
- 多设备并发
- 图像识别自动校准
- 复杂 UI 元素识别
- 无人值守大规模 farm

这些会把项目复杂度直接抬高，但对“先跑通 iPhone 自动录制与人物控制”帮助不大。

## 风险清单

### 1. 真机签名与会话启动成本高

Appium 官方文档明确指出，iOS 真机自动化比模拟器复杂得多，主要受 Apple 真机限制影响。

### 2. 坐标空间可能不是面板像素

这是最大风险。

如果直接拿 iPhone 面板分辨率做映射，可能会因为：

- Retina scale
- safe area
- active application rect

导致点击偏移。

所以建议以 `viewport rect` 作为 iOS runtime 坐标空间。

### 3. 游戏类场景比普通 App 更脆弱

游戏不是标准表单 UI，WDA/Appium 能做的是触控注入，不是游戏专用 automation framework。

因此必须接受：

- 需要额外 timing 调整
- 某些动作要单独校准
- 长流程稳定性会弱于 Android ADB

## 建议的首个实现顺序

1. 先做 `tap/swipe + viewport scaling`
2. 用最短 route 跑通人物移动
3. 再接 `record_start/record_stop`
4. 最后才做 `teleport`

不要一开始就把录屏、地图、路径切段、profile 校准一起上。

## 参考资料

- Appium XCUITest Driver Overview  
  [https://appium.github.io/appium-xcuitest-driver/](https://appium.github.io/appium-xcuitest-driver/)

- Appium XCUITest Real Device Configuration  
  [https://appium.github.io/appium-xcuitest-driver/6.0/preparation/real-device-config/](https://appium.github.io/appium-xcuitest-driver/6.0/preparation/real-device-config/)

- Appium XCUITest Gestures  
  [https://appium.github.io/appium-xcuitest-driver/10.14/guides/gestures/](https://appium.github.io/appium-xcuitest-driver/10.14/guides/gestures/)

- Appium XCUITest Commands: `mobile: tap` / recording screen  
  [https://appium.github.io/appium-xcuitest-driver/7.0/reference/commands/](https://appium.github.io/appium-xcuitest-driver/7.0/reference/commands/)

- Appium Start Screen Recording  
  [https://appium.github.io/appium.io/docs/en/commands/device/recording-screen/start-recording-screen/](https://appium.github.io/appium.io/docs/en/commands/device/recording-screen/start-recording-screen/)

- WebDriverAgent archived repository  
  [https://github.com/facebookarchive/WebDriverAgent](https://github.com/facebookarchive/WebDriverAgent)

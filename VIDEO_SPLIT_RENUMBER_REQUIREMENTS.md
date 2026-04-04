# Video Split And Renumber Requirements

## Implementer Prompt (English)

```text
Please implement the v5 post-processing video split-and-renumber workflow described in this document and in VIDEO_SPLIT_RENUMBER_CHECKLIST.md.

Relevant files to inspect first:
- engine/route_segments.py
- engine/runner.py
- engine/shared_runner.py

Core requirements:
1. Do not change route semantics or runtime action execution.
2. Do not split during recording.
3. Record the original segment normally first, then process that original segment directory immediately after it has been fully written.
4. Precompute the final numbering plan from the route definitions before processing outputs.
5. Only process recorded segments, i.e. content between record_start and record_stop.
6. Clip planning must be based on the route-declared duration, not on the probed media duration.
7. Split rule for planning:
   - if route-declared duration t_route < 5 seconds, keep the segment as one final clip
   - if route-declared duration t_route >= 5 seconds, planned clip count = floor(t_route / 5)
   - this planned count is what drives numbering
8. Actual output rule:
   - generate the planned number of clips from the start of the recorded file
   - for non-final planned clips, target 5 seconds each
   - for the final planned clip, clamp the end to the actual media duration if the file is slightly shorter than the route-declared duration
   - do not drop the last planned clip just because the actual file is slightly short, e.g. 10.0 declared but 9.8 recorded
9. Tail dropping only applies to the intentional remainder implied by the route-declared duration rule, not to small recorder shortfall around the planned boundary.
10. Recommended validation: if the actual media duration is shorter than the planned end by more than a small tolerance such as 0.5 seconds, emit a warning or fail the segment.
11. Renumber within the same route + label only.
12. Different labels must not affect each other.
13. Different routes must not affect each other.
14. Do not use part1, part2, chunk01, or s01.
15. Final naming must stay in the existing format:
    <video_base>/<label>/<country>_r<route:02d>_<label><occurrence:02d>/<config_id>.mp4
16. If one original segment expands into multiple final clips, later clips with the same route + label must shift forward accordingly.
17. Preserve the original config_id.mp4 filenames inside the final directories.
18. Splitting is directory-scoped: if one original segment directory is processed, every config video inside that directory must be processed consistently.
19. Prefer writing into final output directories instead of overwriting in place.
20. Provide a dry-run mode first.
21. Dry-run must print at least:
   - source original segment directory
   - route-declared duration
   - original duration
   - planned final clip count
   - whether route-rule tail content will be dropped
   - whether the actual file undershoots the planned end
   - computed final target directories
   - final numbering mapping

Acceptance criteria for the current natlan route set:
- 64 original recorded segments
- 90 final segments after expansion
- 19 original segments with dropped tail content
- 34 seconds of total dropped tail content
- all emitted clips are exactly 5 seconds, except:
  - original segments shorter than 5 seconds, which remain unchanged
  - the final planned clip, which may be slightly shorter when the actual recorded file undershoots the route-declared duration a little
- numbering is continuous within each route + label, with no duplicates or gaps

Please implement the feature end-to-end, add any needed helper code, and report:
- which files you changed
- how the split plan is computed
- how you validated the 64 -> 90 result
- any edge cases or assumptions
```

## 目的

为 v5 录制结果增加一个后处理步骤：

1. 先按现有 runner 正常录制原始视频
2. 对每个原始录制段目录做切分或保留
3. 按切分后的最终结果，重新计算同一 `route + label` 内的编号

这个需求只针对录制结果后处理。
不修改 route 语义，不修改运行时动作执行，不要求在录制器执行中途切视频。

## 当前命名规则

当前 v5 的单段录制目录命名为：

```text
<video_base>/<label>/<country>_r<route:02d>_<label><occurrence:02d>/<config_id>.mp4
```

例如：

```text
recordings/huaweimate/run/natlan_r01_run01/Medium_30_Low_Low.mp4
```

这里的 `run01` 含义是：

- `route = 01`
- `label = run`
- 这是该 route 内第 1 个 `run` 录制段

注意：

- 当前不是 `s01 / s02 / s03` 的统一全局段号
- 当前编号只在同 route + 同 label 内递增

## 新规则

切分后的编号规则改为：

> 对每个 `route + label`，按最终视频顺序，从 `01` 开始连续编号。

同时，单个原始录制段的处理规则固定如下：

- 先用 route 里声明的动作时长 `t_route` 计算最终应有多少段
- 若 `t_route < 5` 秒，则保留原视频，作为 `1` 个最终段
- 若 `t_route >= 5` 秒，则最终片段数为 `floor(t_route / 5)`
- 这个片段数用于最终编号规划
- 实际切视频时，再读取文件真实时长 `t_media`
- 对前面的计划片段，目标长度仍然是 `5s`
- 对最后一个计划片段，如果 `t_media` 比理论结束点略短，例如 `10s` 实录成 `9.8s`，则最后一段直接截到文件结尾，不因此少一段
- 只有 route 规则本来就决定要丢弃的余数才丢弃，例如 `8s -> 1 x 5s`
- 不做均分
- 不做补齐
- 不做时间拉伸

也就是说：

- `4s` -> 保留 `4s`
- `4.5s` -> 保留 `4.5s`
- `5s` -> `5s`
- `6s` -> `5s`，丢弃最后 `1s`
- `7s` -> `5s`，丢弃最后 `2s`
- `8s` -> `5s`，丢弃最后 `3s`
- `9s` -> `5s`，丢弃最后 `4s`
- `10s` -> `5s + 5s`
- route 写 `10s`，实际录到 `9.8s` -> `5s + 4.8s`

这是一个故意允许按 route 规则截尾的规则。实现者不应尝试保留 route 规则本身决定丢弃的余数，但也不应因为录制器轻微短录就误少一段。

## 当前项目快照

基于当前 `routes/natlan/*.py` 的统计结果：

- 原始录制段总数：`64`
- 最终总段数：`90`
- 会被截掉尾部的原始录制段：`19`
- 被丢弃的尾部总时长：`34s`
- 原始时长低于 `5s`、因此原样保留的段：`2`

这个统计只作为当前路线集的参考快照，不应在实现中写死。

补充说明：

- 上面的 `64 -> 90` 统计仍然按 route 声明时长计算
- 录制器实际文件若出现 `9.8s`、`9.7s` 这种轻微短录，不应改变段数规划

## 切分单位

切分单位是“一个原始录制目录中的所有配置视频”。

例如当前目录：

```text
recordings/huaweimate/run/natlan_r01_run01/
  High_60_Low_Low.mp4
  Medium_30_Low_Low.mp4
  ...
```

如果这个原始录制段需要处理，则：

- 该目录下每个 `config_id.mp4` 都必须按同一规则处理
- 不能只处理其中某一个配置文件
- 不能让同目录下不同配置得到不同段数
- 同目录下的最终片段数必须由 route 规划统一决定，不能由某个配置视频的实际探测时长单独决定

## 处理时机

处理时机要求如下：

- 不是等所有 route / 所有动作 / 所有视频全部录完之后再统一处理
- 而是单个原始录制段目录的数据已经保存完成后，就立刻执行该段的最终输出处理

但是：

- 在开始实际输出前，仍然要先根据 route 定义预计算该 route 内的最终重编号计划

也就是说：

- 编号规划先算好
- 视频处理按单个原始录制段目录完成的粒度即时执行

## 最终命名规则

最终目录命名仍然沿用当前格式：

```text
<video_base>/<label>/<country>_r<route:02d>_<label><occurrence:02d>/<config_id>.mp4
```

不引入：

- `part1`
- `part2`
- `s01`
- `chunk01`

也就是说，最终结果会直接进入正常的 `run01`、`run02`、`run03` 这种编号体系。

## 例子 1：r01 第一个 run(10)

当前 [routes/natlan/1.py](/Users/xingzhengpeng/CODEZONE/PCO/Power-Optimization/DATA COLLECTION/Auto_Scripts_v5/routes/natlan/1.py) 的前两个录制段是：

1. `run(10)`
2. `climb(8)`

如果设备是 `huaweimate`，原始保存路径中，第一个 `run(10)` 当前应为：

```text
recordings/huaweimate/run/natlan_r01_run01/<config_id>.mp4
```

切分并重排后，应变为两个最终目录：

```text
recordings/huaweimate/run/natlan_r01_run01/<config_id>.mp4
recordings/huaweimate/run/natlan_r01_run02/<config_id>.mp4
```

含义：

- `run01`：原始 `run(10)` 的前 `5s`
- `run02`：原始 `run(10)` 的后 `5s`

如果这个目录下某个实际文件只录到 `9.8s`，那么也仍然要输出：

- `run01`：`0.0s ~ 5.0s`
- `run02`：`5.0s ~ 9.8s`

不能因为 `9.8 < 10.0` 就把 `run02` 整段丢掉。

同一个 route 里的 `climb(8)` 是不同 label，因此它最终仍然是：

```text
recordings/huaweimate/climb/natlan_r01_climb01/<config_id>.mp4
```

但这个 `climb01` 只保留前 `5s`，最后 `3s` 会被丢弃。

## 例子 2：同 label 后续编号顺延

假设某条 route 在同一个 `label=run` 下原本有：

```text
run01   <- 10s
run02   <- 6s
run03   <- 5s
```

按新规则处理后最终应为：

```text
run01   <- 原 run01 的前 5s
run02   <- 原 run01 的后 5s
run03   <- 原 run02 的前 5s
run04   <- 原 run03 的 5s
```

这里的关键要求是：

- 后续同 label 的编号必须整体顺延
- 原 `run02` 的最后 `1s` 会被丢弃

## 重排范围

重排只在下列范围内进行：

- 同一个 `video_base`
- 同一个 `route_suffix`
- 同一个 `label`

以下对象不受影响：

- 别的 route
- 同 route 下别的 label
- 别的设备目录

## 输入假设

实现者可以假设输入录制目录已经满足当前 v5 命名规则，类似：

```text
recordings/<device>/<label>/natlan_rXX_<label>NN/<config_id>.mp4
```

实现者也可以直接依赖当前 route 文件来判断：

- 哪些段被录制
- 每段的动作 label
- 每段的动作时长

## 推荐实现流程

推荐按下面流程实现：

1. 读取 `routes/natlan/*.py`
2. 提取所有原始录制段
3. 对每个原始录制段，先根据 route 声明时长计算最终应展开成多少段
4. 规则固定为：
   - `t_route < 5` -> `1` 段
   - `t_route >= 5` -> `floor(t_route / 5)` 段
5. 在每个 `route + label` 内，按最终展开结果重新编号
6. 单个原始录制段目录写完后，处理该目录下的全部 `config_id.mp4`
7. 读取每个实际视频文件的真实时长 `t_media`
8. 若 `t_route < 5`，则直接写入最终目录
9. 若 `t_route >= 5`，则按规划导出 `[0,5)`, `[5,10)`, `[10,15)` 这类连续窗口
10. 对最后一个计划片段，结束时间取 `min(计划结束点, t_media)`
11. route 规则本来就不保留的余数继续丢弃
12. 不保留旧的临时命名

## 工程要求

- 先做 dry-run
- dry-run 至少打印：
- 原始目录
- route 声明时长
- 原始时长
- 最终片段数
- 是否会按 route 规则截掉尾部
- 是否存在实际短录
- 切分后目标目录
- 最终编号映射
- 实际执行时优先输出到新目录，避免原地覆盖

## 验收

- 当前 natlan 路线集应当得到 `64 -> 90`
- 所有最终片段都应满足：
  - 要么是原始时长低于 `5s` 的保留段
  - 要么是严格的 `5s` 片段
  - 要么是因为实际录制轻微短于 route 声明时长，而导致最后一个计划片段略短
- 同 `route + label` 编号连续，无重复、无跳号
- 最终目录中仍然使用原始 `config_id.mp4` 文件名
- 当前 natlan 路线集应能验证出：
  - `19` 个原始段发生截尾
  - 总截尾时长为 `34s`

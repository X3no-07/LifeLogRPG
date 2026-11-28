extends "res://scripts/launcher_ui.gd"

const ReplayScene := preload("res://scenes/main.tscn")
const LAST_REPLAY_PATH := "user://last-replay.txt"
const DEVELOPMENT_SAMPLE := "res://saved_logs/log_wangfujing_art.json"
const BUNDLED_SAMPLE := "res://saved_logs/log_coords_route.json"
const START_WORKER := "import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); runpy.run_module('baker.launcher_worker',run_name='__main__',alter_sys=True)"
const READ_KEYS := "import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); runpy.run_module('baker.local_keys',run_name='__main__',alter_sys=True)"
const LOCAL_KEYS := "user://local-keys.dpapi"
const BAKE_TIMEOUT_SECONDS := 180
const BAKE_STAGES := {
    "extract": "解析日记",
    "lookup": "查找地点",
    "route": "查询路线",
    "map": "下载 OpenStreetMap 路网",
    "nearby": "查询沿途地点",
    "build": "整理路线和地图",
    "story": "生成回放文案",
    "render": "绘制像素地图",
}

var _replay_scene: Node
var _last_replay := ""
var _job_dir := ""
var _worker_pid := -1
var _worker_timer: Timer
var _worker_started_msec := 0
var _elapsed_seconds := -1
var _stage_label := ""
var _search_timer: Timer
var _search_field := -1
var _search_text := ""
var _search_pid := -1
var _search_dir := ""
var _search_started := 0


func _ready() -> void:
    if _start_in_replay():
        get_tree().call_deferred("change_scene_to_packed", ReplayScene)
        return

    super._ready()
    run_requested.connect(_generate)
    sample_requested.connect(_open_sample)
    replay_requested.connect(_open_last_replay)
    cancel_requested.connect(_cancel_worker)
    place_search_requested.connect(_queue_place_search)
    _restore_local_keys()

    _worker_timer = Timer.new()
    _worker_timer.wait_time = 0.25
    _worker_timer.timeout.connect(_check_worker)
    add_child(_worker_timer)
    _search_timer = Timer.new()
    _search_timer.timeout.connect(_poll_place_search)
    add_child(_search_timer)

    if FileAccess.file_exists(LAST_REPLAY_PATH):
        _last_replay = FileAccess.get_file_as_string(LAST_REPLAY_PATH).strip_edges()
    set_replay_available(not _last_replay.is_empty() and FileAccess.file_exists(_last_replay))


func _restore_local_keys() -> void:
    var runtime := OS.get_executable_path().get_base_dir().path_join("runtime")
    if not FileAccess.file_exists(runtime.path_join("remember-local-keys")) or not FileAccess.file_exists(LOCAL_KEYS):
        return
    var output := []
    if OS.execute(runtime.path_join("python/python.exe"),
            ["-B", "-X", "utf8", "-c", READ_KEYS, runtime, ProjectSettings.globalize_path(LOCAL_KEYS)], output) != 0 or output.is_empty():
        return
    var keys: Variant = JSON.parse_string(output[0])
    if keys is Dictionary:
        _amap.text = str(keys.get("amap_key", ""))
        _deepseek.text = str(keys.get("deepseek_key", ""))


func _start_in_replay() -> bool:
    if not OS.get_environment("LIFELOG_JSON").is_empty():
        return true
    for argument in OS.get_cmdline_args():
        if argument.begins_with("--log="):
            return true
    return OS.has_feature("editor") and DisplayServer.get_name() == "headless"


func _open_sample() -> void:
    var sample := OS.get_executable_path().get_base_dir().path_join("sample/route.json")
    if not FileAccess.file_exists(sample):
        sample = DEVELOPMENT_SAMPLE if FileAccess.file_exists(DEVELOPMENT_SAMPLE) else BUNDLED_SAMPLE
    _open_replay(sample)


func _open_last_replay() -> void:
    if not _last_replay.is_empty():
        _open_replay(_last_replay)


func _open_replay(path: String) -> void:
    if is_instance_valid(_replay_scene):
        return
    if not FileAccess.file_exists(path):
        show_status("回放文件已移动或删除。请重新生成。", true)
        return
    _replay_scene = ReplayScene.instantiate()
    _replay_scene.set("log_path", path)
    _replay_scene.set("launcher_managed", true)
    _replay_scene.connect("return_requested", _close_replay)
    hide()
    add_sibling(_replay_scene)


func _close_replay() -> void:
    _replay_scene.queue_free()
    _replay_scene = null
    show()


func _generate(mode: String, input: String, duration: float, amap_key: String, deepseek_key: String, city: String) -> void:
    if _worker_pid != -1:
        return
    _stop_place_search()
    var packaged_root := OS.get_executable_path().get_base_dir().path_join("runtime")
    var worker_root := packaged_root
    var python := worker_root.path_join("python/pythonw.exe")
    if OS.has_feature("editor") and not FileAccess.file_exists(python):
        worker_root = ProjectSettings.globalize_path("res://")
        python = OS.get_environment("LIFELOG_PYTHON")
        if python.is_empty():
            python = "pythonw.exe" if OS.get_name() == "Windows" else "python3"
    elif not FileAccess.file_exists(python):
        show_status("没有找到随附的 Python。请将 EXE 和 runtime 文件夹放在一起。", true)
        return

    var job_name := "%d-%d-%08x" % [int(Time.get_unix_time_from_system()), Time.get_ticks_usec(), randi()]
    _job_dir = ProjectSettings.globalize_path("user://bakes/" + job_name).replace("\\", "/")
    var output_dir := _job_dir.path_join("output")
    if DirAccess.make_dir_recursive_absolute(output_dir) != OK:
        show_status("无法创建回放目录。请检查磁盘空间和当前账户的写入权限。", true)
        return
    var request_path := _job_dir.path_join("request.json")
    var request := FileAccess.open(request_path, FileAccess.WRITE)
    if request == null:
        show_status("无法写入生成请求。请检查当前账户的写入权限。", true)
        return
    request.store_string(JSON.stringify({
        "mode": mode,
        "input": input,
        "duration": duration,
        "output_dir": output_dir,
        "amap_key": amap_key,
        "deepseek_key": deepseek_key,
        "city": city,
        "selected_places": selected_route_places(),
    }))
    request.close()

    var args := PackedStringArray(["-B", "-X", "utf8", "-c", START_WORKER, worker_root, request_path])
    if FileAccess.file_exists(packaged_root.path_join("remember-local-keys")):
        args.append(ProjectSettings.globalize_path(LOCAL_KEYS))
    _worker_pid = OS.create_process(python, args)
    if _worker_pid == -1:
        DirAccess.remove_absolute(request_path)
        show_status("无法启动 Python。请检查 runtime 文件夹或开发环境的 Python 路径。", true)
        return
    set_busy(true)
    _worker_started_msec = Time.get_ticks_msec()
    _elapsed_seconds = 0
    _stage_label = "启动生成程序"
    show_status("%s · 已用 0 秒" % _stage_label)
    _worker_timer.start()


func _queue_place_search(index: int, query: String) -> void:
    _stop_place_search()
    show_place_choices(-1, [], "")
    if not is_instance_valid(_search_timer) or index < 0 or query.length() < 2 or _busy:
        return
    if _amap.text.strip_edges().is_empty():
        show_place_choices(index, [], "填写高德 Web 服务 Key 后即可搜索。")
        return
    _search_field = index
    _search_text = query
    _search_timer.start(0.35)


func _poll_place_search() -> void:
    if _search_pid == -1:
        _launch_place_search()
        return
    var result_path := _search_dir.path_join("result.json")
    if FileAccess.file_exists(result_path):
        var result: Variant = JSON.parse_string(FileAccess.get_file_as_string(result_path))
        var index := _search_field
        _stop_place_search(false)
        if result is Dictionary and result.get("ok", false):
            var choices: Array = result.get("choices", [])
            var label := "选择起点" if index == 0 else "选择终点"
            if choices.is_empty():
                label = "高德没有返回可定位的候选。试试简称、附近地标或门牌号。"
            show_place_choices(index, choices, label)
        else:
            show_place_choices(index, [], str(result.get("message", "地点查询失败。")) if result is Dictionary else "地点查询失败。")
    elif not OS.is_process_running(_search_pid) or Time.get_ticks_msec() - _search_started > 10000:
        _stop_place_search()
        show_place_choices(-1, [], "地点搜索超时或提前结束，可以修改关键词再试。")


func _launch_place_search() -> void:
    var packaged_root := OS.get_executable_path().get_base_dir().path_join("runtime")
    var worker_root := packaged_root
    var python := worker_root.path_join("python/pythonw.exe")
    if OS.has_feature("editor"):
        worker_root = ProjectSettings.globalize_path("res://")
        python = OS.get_environment("LIFELOG_PYTHON")
    _search_dir = ProjectSettings.globalize_path("user://place-search/%d-%08x" % [Time.get_ticks_usec(), randi()])
    var request_path := _search_dir.path_join("request.json")
    if DirAccess.make_dir_recursive_absolute(_search_dir) == OK:
        var file := FileAccess.open(request_path, FileAccess.WRITE)
        if file != null:
            file.store_string(JSON.stringify({
                "mode": "suggest", "query": _search_text, "city": _city.text.strip_edges(),
                "amap_key": _amap.text.strip_edges(), "deepseek_key": _deepseek.text.strip_edges(),
            }))
            file.close()
            var args := PackedStringArray(["-B", "-X", "utf8", "-c", START_WORKER, worker_root, request_path])
            if FileAccess.file_exists(packaged_root.path_join("remember-local-keys")):
                args.append(ProjectSettings.globalize_path(LOCAL_KEYS))
            if not python.is_empty():
                _search_pid = OS.create_process(python, args)
    if _search_pid == -1:
        _stop_place_search()
        show_place_choices(-1, [], "无法启动地点搜索。请检查 runtime 文件夹。")
        return
    _search_started = Time.get_ticks_msec()
    show_place_choices(_search_field, [], "正在搜索地点…")
    _search_timer.start(0.12)


func _stop_place_search(kill_process: bool = true) -> void:
    if is_instance_valid(_search_timer):
        _search_timer.stop()
    if kill_process and _search_pid != -1 and OS.is_process_running(_search_pid):
        OS.kill(_search_pid)
    _search_pid = -1
    _search_field = -1
    if not _search_dir.is_empty():
        for filename in ["request.json", "result.json", "result.json.tmp"]:
            var path := _search_dir.path_join(filename)
            if FileAccess.file_exists(path):
                DirAccess.remove_absolute(path)
        DirAccess.remove_absolute(_search_dir)
        _search_dir = ""


func _check_worker() -> void:
    var result_path := _job_dir.path_join("result.json")
    if FileAccess.file_exists(result_path):
        var result: Variant = JSON.parse_string(FileAccess.get_file_as_string(result_path))
        _finish_worker(result)
        return
    if not OS.is_process_running(_worker_pid):
        _finish_worker(null)
        return

    var progress_path := _job_dir.path_join("progress.json")
    var stage := _stage_label
    if FileAccess.file_exists(progress_path):
        var progress: Variant = JSON.parse_string(FileAccess.get_file_as_string(progress_path))
        if progress is Dictionary:
            stage = BAKE_STAGES.get(progress.get("stage"), _stage_label)
    var elapsed := floori(float(Time.get_ticks_msec() - _worker_started_msec) / 1000.0)
    if elapsed >= BAKE_TIMEOUT_SECONDS:
        _stop_worker()
        _clear_worker()
        show_status("生成超过 %d 秒，已停止。最后一步是「%s」。可以检查网络后重试。" % [BAKE_TIMEOUT_SECONDS, stage], true)
    elif elapsed != _elapsed_seconds or stage != _stage_label:
        _elapsed_seconds = elapsed
        _stage_label = stage
        show_status("%s · 已用 %d 秒" % [_stage_label, _elapsed_seconds])


func _cancel_worker() -> void:
    if _worker_pid == -1:
        return
    _stop_worker()
    _clear_worker()
    show_status("已取消生成，可以修改输入后重试。")


func _stop_worker() -> void:
    if _worker_pid != -1 and OS.is_process_running(_worker_pid):
        OS.kill(_worker_pid)


func _remove_request() -> void:
    var request_path := _job_dir.path_join("request.json")
    if FileAccess.file_exists(request_path):
        DirAccess.remove_absolute(request_path)


func _clear_worker() -> void:
    _worker_timer.stop()
    _worker_pid = -1
    _remove_request()
    set_busy(false)


func _finish_worker(result: Variant) -> void:
    _clear_worker()
    if not result is Dictionary:
        show_status("生成程序提前退出。请确认 runtime 文件完整后重试。", true)
        return
    if not bool(result.get("ok", false)):
        show_status(str(result.get("message", "生成失败，请检查输入。")), true)
        return

    var path := str(result.get("log_path", "")).replace("\\", "/").simplify_path()
    if path.get_base_dir() != _job_dir.path_join("output") or not FileAccess.file_exists(path):
        show_status("生成的回放文件无法读取。", true)
        return
    _last_replay = path
    var last := FileAccess.open(LAST_REPLAY_PATH, FileAccess.WRITE)
    if last:
        last.store_string(path)
        last.close()
    set_replay_available(true)
    show_status("已生成回放。")
    _open_replay(path)


func _exit_tree() -> void:
    _stop_place_search()
    if _worker_pid != -1:
        _stop_worker()
        _remove_request()

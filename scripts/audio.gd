extends Node
class_name AudioSystem
# AudioSystem - 8-Bit BGM 程序化生成 + 播放
#
# 不用外部 .ogg/.wav 素材, 直接用 AudioStreamWAV + PCM 字节生成 chiptune 旋律
# 4 音符 8-bit 方波 + 衰减, 4 秒 loop
#
# 用法:
#   var audio = AudioSystem.new()
#   add_child(audio)
#   audio.setup()
#   audio.play_music()
#
# 后续可扩展: 根据 meta.mood / meta.weather 切不同旋律 (P2.3+)

var _player: AudioStreamPlayer
var _stream: AudioStreamWAV


func setup() -> void:
    _player = AudioStreamPlayer.new()
    _player.bus = "Master"
    _player.volume_db = -8.0
    add_child(_player)
    _stream = _generate_chiptune()
    _player.stream = _stream


func play_music() -> void:
    if _player and _stream:
        _player.play()


func stop_music() -> void:
    if _player:
        _player.stop()


func set_volume_db(db: float) -> void:
    if _player:
        _player.volume_db = db


# ----------------------------------------------------------------------------
#  程序化生成 8-bit chiptune
# ----------------------------------------------------------------------------

func _generate_chiptune() -> AudioStreamWAV:
    """生成 4 音符 C-E-G-E 8-bit 方波, 4 秒 loop"""
    var rate := 22050
    var duration := 4.0
    var samples := int(rate * duration)
    var data := PackedByteArray()
    data.resize(samples)
    # 4 音符 C4 E4 G4 E4 (Hz)
    var notes := [262, 330, 392, 330]
    var note_len := samples / 4
    for i in range(samples):
        var note_idx: int = i / note_len
        var freq: int = notes[note_idx]
        var phase: float = fmod(float(i) * freq / rate, 1.0)
        # 方波 (50% duty)
        var amp: int = 80 if phase < 0.5 else -80
        # 衰减 (每音符尾衰减 50%)
        var pos_in_note: float = fmod(float(i), float(note_len))
        var decay: float = 1.0 - (pos_in_note / float(note_len)) * 0.4
        # 8-bit unsigned (0-255, 中心 128)
        var sample: int = int(amp * decay) + 128
        sample = clamp(sample, 0, 255)
        data[i] = sample
    var s := AudioStreamWAV.new()
    s.format = AudioStreamWAV.FORMAT_8_BITS
    s.mix_rate = rate
    s.stereo = false
    s.data = data
    s.loop_mode = AudioStreamWAV.LOOP_FORWARD
    s.loop_begin = 0
    s.loop_end = samples
    return s

from core.local_tts_bundle import (
    inspect_local_tts_bundle, inspect_noir_voice_assets, make_noir_inference_config,
)


def test_integrated_gpt_sovits_bundle_detection(tmp_path):
    root = tmp_path / "GPT-SoVITS"
    runtime = root / "runtime"
    runtime.mkdir(parents=True)
    (runtime / "python.exe").write_bytes(b"")
    (root / "api_v2.py").write_text("# api", encoding="utf-8")
    (root / "configs").mkdir()
    config = root / "configs" / "tts_infer.yaml"
    config.write_text("custom: {}", encoding="utf-8")

    bundle = inspect_local_tts_bundle(str(root), "configs/tts_infer.yaml")

    assert bundle.ready
    assert bundle.python == runtime / "python.exe"
    assert bundle.api_script == root / "api_v2.py"
    assert bundle.config == config


def test_integrated_bundle_reports_missing_runtime(tmp_path):
    root = tmp_path / "GPT-SoVITS"
    root.mkdir()
    (root / "api_v2.py").write_text("# api", encoding="utf-8")

    bundle = inspect_local_tts_bundle(str(root))

    assert not bundle.ready
    assert "runtime" in bundle.message


def test_empty_bundle_selection_does_not_inspect_current_directory():
    bundle = inspect_local_tts_bundle("")

    assert not bundle.ready
    assert "尚未选择" in bundle.message


def test_cpu_default_path_explains_that_the_optional_package_is_not_installed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    bundle = inspect_local_tts_bundle("vendor/gpt_sovits_cpu")

    assert not bundle.ready
    assert "CPU 兼容包尚未安装" in bundle.message


def test_noir_assets_and_generated_config_require_all_runtime_parts(tmp_path, monkeypatch):
    project = tmp_path / "moepet"
    assets_dir = project / "voice_assets" / "noir"
    assets_dir.mkdir(parents=True)
    (assets_dir / "noir-e15.ckpt").write_bytes(b"gpt")
    (assets_dir / "noir_e8_s968.pth").write_bytes(b"sovits")
    (assets_dir / "reference.wav").write_bytes(b"RIFF")
    (assets_dir / "reference.txt").write_text("reference", encoding="utf-8")
    (assets_dir / "reference_zh.txt").write_text("中文释义", encoding="utf-8")
    bundle_root = tmp_path / "bundle"
    (bundle_root / "runtime").mkdir(parents=True)
    (bundle_root / "runtime" / "python.exe").write_bytes(b"")
    (bundle_root / "api_v2.py").write_text("# api", encoding="utf-8")
    for name in ("chinese-hubert-base", "chinese-roberta-wwm-ext-large"):
        (bundle_root / "GPT_SoVITS" / "pretrained_models" / name).mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))

    assets = inspect_noir_voice_assets(project)
    config = make_noir_inference_config(inspect_local_tts_bundle(str(bundle_root)), assets, "cuda")

    assert assets.ready
    assert assets.reference_text_zh == "中文释义"
    content = config.read_text(encoding="utf-8")
    assert "device: cuda" in content
    assert str(assets.gpt_weight).replace("\\", "/") in content

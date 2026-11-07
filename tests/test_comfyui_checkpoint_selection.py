from app.comfyui import _select_image_checkpoint


def test_prefers_configured_sd15_over_first_audio_checkpoint():
    selected, error = _select_image_checkpoint(
        ["ace_step_v1_3.5b.safetensors", "v1-5-pruned-emaonly.safetensors"],
        "v1-5-pruned-emaonly.safetensors",
    )
    assert selected == "v1-5-pruned-emaonly.safetensors"
    assert error is None


def test_missing_configured_checkpoint_does_not_silently_fallback():
    selected, error = _select_image_checkpoint(
        ["ace_step_v1_3.5b.safetensors", "v1-5-pruned-emaonly.safetensors"],
        "missing.safetensors",
    )
    assert selected is None
    assert "missing.safetensors" in error


def test_without_preference_avoids_audio_checkpoint():
    selected, error = _select_image_checkpoint(
        ["ace_step_v1_3.5b.safetensors", "v1-5-pruned-emaonly.safetensors"],
        "",
    )
    assert selected == "v1-5-pruned-emaonly.safetensors"
    assert error is None


def test_audio_only_checkpoint_list_is_rejected():
    selected, error = _select_image_checkpoint(["ace_step_v1_3.5b.safetensors"], "")
    assert selected is None
    assert "오디오 모델" in error

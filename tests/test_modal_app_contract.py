from __future__ import annotations

import ast
from pathlib import Path


APP_PATH = Path("modal_apps/flux2_klein_reference.py")
MODEL_ID = "black-forest-labs/FLUX.2-klein-4B"
MODEL_REVISION = "e7b7dc27f91deacad38e78976d1f2b499d76a294"


def source() -> str:
    assert APP_PATH.exists(), "Modal deployment file must exist"
    return APP_PATH.read_text(encoding="utf-8")


def assigned_constants(text: str) -> dict[str, object]:
    tree = ast.parse(text)
    output: dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        try:
            output[target.id] = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            pass
    return output


def test_deployment_pins_model_and_inference_dependency_versions() -> None:
    values = assigned_constants(source())
    assert values["APP_NAME"] == "thrumely-flux2-klein-reference"
    assert values["MODEL_ID"] == MODEL_ID
    assert values["MODEL_REVISION"] == MODEL_REVISION
    assert values["VOLUME_NAME"] == "thrumely-flux2-klein-4b-weights"
    assert values["MODEL_DIR"] == "/models/flux2-klein-4b"
    assert values["MODAL_VERSION"] == "1.5.3"
    assert values["TORCH_VERSION"] == "2.13.0"
    assert values["DIFFUSERS_VERSION"] == "0.40.0"
    assert values["TRANSFORMERS_VERSION"] == "5.16.1"
    assert values["ACCELERATE_VERSION"] == "1.14.0"
    assert values["HUGGINGFACE_HUB_VERSION"] == "1.29.0"
    assert values["INFERENCE_STEPS"] == 4
    assert values["GUIDANCE_SCALE"] == 1.0


def test_deployment_uses_bounded_zero_idle_l4_class_and_persistent_volume() -> None:
    text = source()
    assert 'modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)' in text
    assert 'volumes={"/models": model_volume}' in text
    assert 'gpu="L4"' in text
    assert "min_containers=0" in text
    assert "max_containers=1" in text
    assert "scaledown_window=60" in text
    assert "retries=0" in text
    assert "@modal.enter()" in text
    assert "@modal.method()" in text


def test_model_download_and_load_are_revision_pinned() -> None:
    text = source()
    assert "snapshot_download(" in text
    assert "repo_id=MODEL_ID" in text
    assert "revision=MODEL_REVISION" in text
    assert "local_dir=MODEL_DIR" in text
    assert "model_volume.commit()" in text
    assert "Flux2KleinPipeline.from_pretrained(" in text
    assert "MODEL_DIR" in text
    assert "torch_dtype=torch.bfloat16" in text
    assert "enable_model_cpu_offload()" in text


def test_inference_contract_supports_generate_and_exact_reference_edit() -> None:
    text = source()
    assert 'operation not in {"generate", "edit_previous"}' in text
    assert 'payload.get("previous_image_base64")' in text
    assert 'operation == "edit_previous"' in text
    assert 'image.format not in {"PNG", "JPEG"}' in text
    assert "image=previous_image" in text
    assert "height=height" in text
    assert "width=width" in text
    assert "num_inference_steps=INFERENCE_STEPS" in text
    assert "guidance_scale=GUIDANCE_SCALE" in text
    assert 'torch.Generator(device="cuda").manual_seed(seed)' in text
    assert 'output.save(buffer, format="PNG")' in text
    assert '"model_revision": MODEL_REVISION' in text


def test_web_endpoint_requires_modal_proxy_auth_and_forwards_only_validated_payload() -> None:
    text = source()
    assert '@modal.fastapi_endpoint(method="POST", requires_proxy_auth=True)' in text
    assert "validated = _validate_payload(payload)" in text
    assert "Flux2KleinReference().infer.remote(validated)" in text
    forbidden = ("MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET", "ak-", "as-")
    for value in forbidden:
        assert value not in text


def test_web_endpoint_omits_unsupported_retry_policy() -> None:
    tree = ast.parse(source())
    infer_function = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "infer"
    )
    app_function_decorator = next(
        decorator
        for decorator in infer_function.decorator_list
        if isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and decorator.func.attr == "function"
    )
    assert all(keyword.arg != "retries" for keyword in app_function_decorator.keywords)

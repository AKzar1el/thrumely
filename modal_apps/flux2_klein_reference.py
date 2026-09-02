from __future__ import annotations

import base64
import io
import time
from typing import Any

import modal

APP_NAME = "thrumely-flux2-klein-reference"
MODEL_ID = "black-forest-labs/FLUX.2-klein-4B"
MODEL_REVISION = "e7b7dc27f91deacad38e78976d1f2b499d76a294"
VOLUME_NAME = "thrumely-flux2-klein-4b-weights"
MODEL_DIR = "/models/flux2-klein-4b"
MODAL_VERSION = "1.5.3"
TORCH_VERSION = "2.13.0"
DIFFUSERS_VERSION = "0.40.0"
TRANSFORMERS_VERSION = "5.16.1"
ACCELERATE_VERSION = "1.14.0"
HUGGINGFACE_HUB_VERSION = "1.29.0"
SAFETENSORS_VERSION = "0.8.0"
INFERENCE_STEPS = 4
GUIDANCE_SCALE = 1.0
_MAX_DIMENSION = 1792
_ALLOWED_DIMENSIONS = {
    (512, 512),
    (768, 512),
    (512, 768),
    (896, 512),
    (512, 896),
    (1024, 1024),
    (1248, 832),
    (832, 1248),
    (1344, 768),
    (768, 1344),
    (1536, 1536),
    (1728, 1152),
    (1152, 1728),
    (1792, 1024),
    (1024, 1792),
}

app = modal.App(APP_NAME)
model_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)

download_image = modal.Image.debian_slim(python_version="3.11").pip_install(
    f"huggingface_hub=={HUGGINGFACE_HUB_VERSION}",
)

inference_image = modal.Image.debian_slim(python_version="3.11").pip_install(
    f"torch=={TORCH_VERSION}",
    f"diffusers=={DIFFUSERS_VERSION}",
    f"transformers=={TRANSFORMERS_VERSION}",
    f"accelerate=={ACCELERATE_VERSION}",
    f"huggingface_hub=={HUGGINGFACE_HUB_VERSION}",
    f"safetensors=={SAFETENSORS_VERSION}",
    "Pillow>=11,<13",
)

web_image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "fastapi>=0.116,<1",
)


def _validate_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")

    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")

    operation = payload.get("operation")
    if operation not in {"generate", "edit_previous"}:
        raise ValueError("operation must be generate or edit_previous")

    width = payload.get("width")
    height = payload.get("height")
    if (
        isinstance(width, bool)
        or isinstance(height, bool)
        or not isinstance(width, int)
        or not isinstance(height, int)
        or width <= 0
        or height <= 0
        or width > _MAX_DIMENSION
        or height > _MAX_DIMENSION
        or width % 16 != 0
        or height % 16 != 0
        or (width, height) not in _ALLOWED_DIMENSIONS
    ):
        raise ValueError("unsupported output dimensions")

    seed = payload.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int) or not (0 <= seed <= 2**32 - 1):
        raise ValueError("seed must be an integer in [0, 2^32-1]")

    previous_image_base64 = payload.get("previous_image_base64")
    if operation == "generate" and previous_image_base64 is not None:
        raise ValueError("generate must not include a previous image")
    if operation == "edit_previous" and (
        not isinstance(previous_image_base64, str) or not previous_image_base64
    ):
        raise ValueError("edit_previous requires a previous image")

    return {
        "prompt": prompt.strip(),
        "operation": operation,
        "width": width,
        "height": height,
        "seed": seed,
        "previous_image_base64": previous_image_base64,
    }


@app.function(
    image=download_image,
    volumes={"/models": model_volume},
    timeout=1800,
    retries=0,
)
def download_model() -> str:
    from huggingface_hub import snapshot_download

    snapshot_download(
        repo_id=MODEL_ID,
        revision=MODEL_REVISION,
        local_dir=MODEL_DIR,
    )
    model_volume.commit()
    return MODEL_REVISION


@app.cls(
    image=inference_image,
    gpu="L4",
    volumes={"/models": model_volume},
    memory=49152,
    min_containers=0,
    max_containers=1,
    scaledown_window=60,
    retries=0,
    timeout=300,
    startup_timeout=600,
)
class Flux2KleinReference:
    @modal.enter()
    def load(self) -> None:
        import torch
        from diffusers import Flux2KleinPipeline

        self.torch = torch
        self.pipe = Flux2KleinPipeline.from_pretrained(
            MODEL_DIR,
            torch_dtype=torch.bfloat16,
        )
        self.pipe.enable_model_cpu_offload()

    @modal.method()
    def infer(self, payload: dict[str, Any]) -> dict[str, Any]:
        from PIL import Image

        validated = _validate_payload(payload)
        prompt = validated["prompt"]
        operation = validated["operation"]
        width = validated["width"]
        height = validated["height"]
        seed = validated["seed"]
        generator = self.torch.Generator(device="cuda").manual_seed(seed)

        started = time.perf_counter()
        if operation == "edit_previous":
            encoded = validated["previous_image_base64"]
            assert isinstance(encoded, str)
            try:
                previous_bytes = base64.b64decode(encoded, validate=True)
                with Image.open(io.BytesIO(previous_bytes)) as image:
                    if image.format not in {"PNG", "JPEG"}:
                        raise ValueError("unsupported previous image format")
                    image.load()
                    previous_image = image.convert("RGB")
            except Exception as exc:
                raise ValueError("previous image must be valid base64 PNG/JPEG") from exc

            output = self.pipe(
                prompt=prompt,
                image=previous_image,
                height=height,
                width=width,
                guidance_scale=GUIDANCE_SCALE,
                num_inference_steps=INFERENCE_STEPS,
                generator=generator,
            ).images[0]
        else:
            output = self.pipe(
                prompt=prompt,
                height=height,
                width=width,
                guidance_scale=GUIDANCE_SCALE,
                num_inference_steps=INFERENCE_STEPS,
                generator=generator,
            ).images[0]
        inference_seconds = time.perf_counter() - started

        buffer = io.BytesIO()
        output.save(buffer, format="PNG")
        media_bytes = buffer.getvalue()
        return {
            "image_base64": base64.b64encode(media_bytes).decode("ascii"),
            "mime_type": "image/png",
            "width": output.width,
            "height": output.height,
            "model_id": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "seed": seed,
            "steps": INFERENCE_STEPS,
            "guidance_scale": GUIDANCE_SCALE,
            "inference_seconds": inference_seconds,
        }


@app.function(image=web_image, timeout=360)
@modal.fastapi_endpoint(method="POST", requires_proxy_auth=True)
def infer(payload: dict[str, Any]):
    from fastapi.responses import JSONResponse

    try:
        validated = _validate_payload(payload)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": {"code": "INVALID_INPUT"}})

    try:
        return Flux2KleinReference().infer.remote(validated)
    except Exception:
        return JSONResponse(status_code=500, content={"error": {"code": "INFERENCE_FAILED"}})

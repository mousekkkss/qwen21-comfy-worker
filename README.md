# Rat Image AI — Qwen Image 2.1 Serverless

> **Retired 2026-10-16.** Qwen Image 2.1 now runs on the main endpoint `satisfied_chocolate_mollusk` (`3rzjn4wbbf66bv`, repository `my-comfy-worker006671`) and loads its models from Cloudflare R2 through that worker's `model_storage` plan. Endpoint `9wyayia4mq5u0w` and template `5gxeancnud` were deleted. Before retirement, `r2_models.py` was verified live on A40: NoctQA + heretic bf16 + FUSAL LoRA hydrated from signed R2 URLs (job `3bb1045c-d8d1-4a32-ab1b-2371ea67bde5-e2`, 1024x1024, 199 s including downloads). This repository is kept for reference.

Dedicated ComfyUI worker for the four Qwen 2.1 website modes. This repository is independent of the existing image/video/training worker.

The workflow rides every request in `input.workflow`; no user workflow or reference image is baked into the image. ComfyUI is pinned to `4ef23c34d950eecc37040a21ee1741a49d2e44b1`. `models.json` pins the verified Comfy-Org Qwen 2.1 revision, filenames, file sizes and hashes. Startup downloads the INT8 DiT, INT8 Qwen3-VL encoder and BF16 VAE (17,283,091,112 bytes). Each worker caches these files on its ephemeral disk. A new worker downloads them again; no persistent network volume is billed.

The website keeps all four original editor JSON files and publishes API adaptations. Editor-only pipes, string controls, switches and preview/sound nodes are resolved in the frontend. The character-sheet adaptation preserves the dependent head/front/side/back passes and saves four images plus a stitched sheet. The text/image-edit mode shares a prompt encoder and supports optional SeedVR2 4K output. The character mode preserves the original character-reference prompt. The Lonecats mode preserves ModelSamplingFlux, EasyCache, its default Base Sigmas/Euler path and Detail Daemon, with optional VOSR2 3x output. All modes share the verified INT8 model set instead of the original machine-specific BF16/GGUF filenames. Experimental inactive sampler branches, vision caption generation and phone/LUT post-effects remain in the original editor files; the website exposes the active generation path and the two upscalers.

## Deploy

GitHub Actions publishes public images to `ghcr.io/mousekkkss/qwen21-comfy-worker`. Pin the published digest in RunPod. The deployed queue endpoint allows A40 and A100 SXM 80GB (`AMPERE_48` and `AMPERE_80`, excluding `NVIDIA RTX A6000` and `NVIDIA A100 80GB PCIe`) with 100 GB disk, min workers 0, max workers 1 and 120s idle timeout. Both pools are enabled after repeated capacity throttling; live flex prices on 2026-09-27 were $1.22/hour for A40 and $2.72/hour for A100. All four generation graphs, VOSR2 and the final signed-link 3840×3840 SeedVR2 download were verified on A40; A100 remains an additional capacity candidate. The optional SeedVR2/VOSR2 nodes download their named upstream model files on first use.

Website routing lives in `qwen21-endpoint-router.js` and the ignored `qwen21-endpoint.local.json`, reusing the API key from `local-runpod.config.json`. The frontend never receives the key. The endpoint's startup health can be checked with `input.mode = qwen21_health`, which returns the registered schemas of the required nodes. A health response does not replace a generation test.

```sh
curl -X POST 'https://api.runpod.ai/v2/9wyayia4mq5u0w/run' \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H 'Content-Type: application/json' \
  --data-binary @request.json
```

Request format: `{"input":{"workflow":{...},"images":[{"name":"reference.png","image":"BASE64"}]}}`. The website may instead send HTTPS signed image URLs. Each loaded image filename must match its upload name.

Outputs use `output.images[]`. The website signs an individual PUT/GET object pair per image in `input.qwen21_output_uploads`; the worker uploads the original PNG bytes and returns `filename`, `type: "url"`, `data`, `url`, `size` and `mime_type`. The website uses its existing local output cache and signed-URL refresh path. No storage credential is placed in this repository or the container. A direct caller may omit upload grants for small base64 responses; a large result without grants fails explicitly rather than overflowing RunPod's result transport. This matters for SeedVR2 4K PNGs and character sheets.

The website's VOSR2 graph splits RGB from alpha before inference, scales the opacity mask, then restores alpha. SeedVR2 natively preserves RGBA. Tests verify byte-preserving result uploads and rejection of mismatched object grants.

## Optional R2 models (DiT, text encoder, LoRA)

Besides the pinned base files, a request may name models stored in Cloudflare R2 (`rat-image-ai-models`, prefix `models/`, folder `Qwen Image`). The website signs one GET URL per file and sends `input.qwen21_model_plan`:

```json
{"provider":"cloudflare-r2","bucket":"rat-image-ai-models","prefix":"models","required":[
  {"relativePath":"loras/Qwen Image/FlatAnime_Qwen_2.1.safetensors","sizeBytes":159436392,"sha256":"…","url":"https://<account>.r2.cloudflarestorage.com/rat-image-ai-models/models/loras/Qwen%20Image/FlatAnime_Qwen_2.1.safetensors?X-Amz-…"}]}
```

`r2_models.py` (installed as `/qwen21_r2_models.py`) accepts at most 12 `.safetensors` files under `diffusion_models/`, `text_encoders/` or `loras/`. Each URL must be HTTPS on `*.r2.cloudflarestorage.com`, address exactly `/<bucket>/<prefix>/<relativePath>` and carry an `X-Amz-Signature`. Size and SHA-256 from the R2 manifest are required. Files of 256 MiB and more download as 64 MiB ranges, 8 at a time (`QWEN21_R2_CONCURRENCY`). Each file is checked for size and SHA-256 before it is moved into `/comfyui/models/...`. A `.r2-verified.json` marker lets later jobs on the same worker reuse the file without downloading or hashing it again. If the disk is short, earlier R2 files that this job does not use are evicted, oldest first. The image holds no storage credential; `QWEN21_R2_BUCKETS` (default `rat-image-ai-models`) only restricts which bucket a plan may name. Hydration runs before the workflow is queued; the result lists the files under `qwen21_models` with `cached` and download seconds.

The workflow refers to the files relative to their model folder, e.g. `UNETLoader.unet_name = "Qwen Image/NoctQA_V1_int8_convrot.safetensors"`. LoRAs are applied with `LoraLoaderModelOnly` between `UNETLoader` and `QwenImage21Cache`. At the pinned ComfyUI commit, the Qwen Image LoRA key map covers the three formats in the bucket: ai-toolkit `diffusion_model.*` (fused `img_mlp.gate_up`), FUSAL `transformer.*` and ModelScope PEFT `*.lora_A.default.weight` (both target `img_mlp.gate_layer`/`proj`, which ComfyUI maps onto halves of the fused weight). NoctQA has the same 649 tensors, dtypes and shapes as the official INT8 DiT. The heretic text encoder has the same 750 keys and shapes as the official `qwen3vl_8b_bf16.safetensors`, so `CLIPLoader(type=qwen_image)` loads it unchanged.

Tests: `python -m unittest discover -s tests -v` covers plan validation (host, path, signature, folder, extension, size/hash), ranged download, hash mismatch cleanup, cache reuse, re-download after a hash change and eviction.

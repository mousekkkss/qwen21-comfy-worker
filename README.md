# Rat Image AI — Qwen Image 2.1 Serverless

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

FROM runpod/worker-comfyui:latest-base@sha256:5ca260328d848eaa7fff4ed46813f31ad39bcae69a17f1f91ae42a80c76d7812
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ARG COMFYUI_REF=4ef23c34d950eecc37040a21ee1741a49d2e44b1
RUN git -C /comfyui fetch --depth 1 origin "$COMFYUI_REF" \
    && git -C /comfyui checkout --detach "$COMFYUI_REF" \
    && python -m pip install --no-cache-dir -r /comfyui/requirements.txt runpod requests websocket-client huggingface_hub \
    && git clone https://github.com/Jonseed/ComfyUI-Detail-Daemon.git /comfyui/custom_nodes/ComfyUI-Detail-Daemon \
    && git -C /comfyui/custom_nodes/ComfyUI-Detail-Daemon checkout 3394e44afea04ed0188fb37b21f0d9952469766b \
    && git clone https://github.com/ylchen333/ComfyUI-VOSR2.git /comfyui/custom_nodes/ComfyUI-VOSR2 \
    && git -C /comfyui/custom_nodes/ComfyUI-VOSR2 checkout 6a21810b3f4f1a0ffc477c55330db0ac03c671f0 \
    && git clone https://github.com/numz/ComfyUI-SeedVR2_VideoUpscaler.git /comfyui/custom_nodes/ComfyUI-SeedVR2_VideoUpscaler \
    && git -C /comfyui/custom_nodes/ComfyUI-SeedVR2_VideoUpscaler checkout 4490bd1f482e026674543386bb2a4d176da245b9 \
    && python -m pip install --no-cache-dir -r /comfyui/custom_nodes/ComfyUI-Detail-Daemon/requirements.txt -r /comfyui/custom_nodes/ComfyUI-VOSR2/requirements.txt -r /comfyui/custom_nodes/ComfyUI-SeedVR2_VideoUpscaler/requirements.txt \
    && cd /comfyui && python main.py --quick-test-for-ci --cpu
COPY qwen21_nodes.py /comfyui/custom_nodes/qwen21_nodes.py
COPY official_handler.py /handler.py
COPY worker.py /qwen21-worker.py
COPY bootstrap.py /bootstrap.py
COPY models.json /models.json
COPY start.sh /qwen21-start.sh
RUN chmod +x /qwen21-start.sh
ENV PYTHONUNBUFFERED=1 COMFY_API_AVAILABLE_MAX_RETRIES=1200 COMFY_API_AVAILABLE_INTERVAL_MS=250
CMD ["/qwen21-start.sh"]

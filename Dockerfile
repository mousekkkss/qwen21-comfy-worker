FROM runpod/worker-comfyui:latest-base@sha256:5ca260328d848eaa7fff4ed46813f31ad39bcae69a17f1f91ae42a80c76d7812
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ARG COMFYUI_REF=4ef23c34d950eecc37040a21ee1741a49d2e44b1
RUN git -C /comfyui fetch --depth 1 origin "$COMFYUI_REF" \
    && git -C /comfyui checkout --detach "$COMFYUI_REF" \
    && python -m pip install --no-cache-dir -r /comfyui/requirements.txt runpod requests websocket-client huggingface_hub \
    && cd /comfyui && python main.py --quick-test-for-ci --cpu
COPY qwen21_nodes.py /comfyui/custom_nodes/qwen21_nodes.py
COPY official_handler.py /handler.py
COPY bootstrap.py /bootstrap.py
COPY models.json /models.json
COPY start.sh /qwen21-start.sh
RUN chmod +x /qwen21-start.sh
ENV PYTHONUNBUFFERED=1 COMFY_API_AVAILABLE_MAX_RETRIES=1200 COMFY_API_AVAILABLE_INTERVAL_MS=250
CMD ["/qwen21-start.sh"]

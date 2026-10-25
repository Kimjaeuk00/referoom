FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/home/app/.cache/huggingface \
    PATH="/opt/venv/bin:$PATH" \
    UV_PYTHON_DOWNLOADS=never

RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir uv==0.12.13 \
 && uv venv --python /usr/local/bin/python /opt/venv

COPY common-py/pyproject.toml common-py/README.md /opt/referoom-common/
COPY common-py/referoom_common/ /opt/referoom-common/referoom_common/
WORKDIR /app/rag-service
COPY rag-service/requirements-data.txt rag-service/requirements-rag.txt ./
# CPU wheels avoid incompatible NVIDIA dependencies on ARM; no model change.
# Preserve A's source requirements; normalize only the image's installation input.
RUN sed '/^[[:space:]]*-e[[:space:]]*\.\.\/common-py/d' requirements-rag.txt > /tmp/requirements-rag.txt \
 && uv pip install --no-cache --torch-backend=cpu --python /opt/venv/bin/python -r requirements-data.txt -r /tmp/requirements-rag.txt /opt/referoom-common \
 && uv pip check --python /opt/venv/bin/python \
 && python -c "import referoom_common, faiss, pypdfium2, sentence_transformers" \
 && rm /tmp/requirements-rag.txt

RUN groupadd --gid 10001 app \
 && useradd --uid 10001 --gid app --create-home app \
 && mkdir -p /home/app/.cache/huggingface \
 && chown -R app:app /app/rag-service /home/app
COPY --chown=app:app rag-service/app/ ./app/
RUN python -c "from pathlib import Path; import importlib.metadata as m, json; assert not list(Path('/app').rglob('.env*')); assert not list(Path('/opt/referoom-common').rglob('.env*')); assert not json.loads(m.distribution('referoom-common').read_text('direct_url.json')).get('dir_info', {}).get('editable', False)"
USER app
EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]

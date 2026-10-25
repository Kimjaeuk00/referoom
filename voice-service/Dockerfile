FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/home/app/.cache/huggingface \
    PATH="/opt/venv/bin:$PATH" \
    UV_PYTHON_DOWNLOADS=never

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg libgomp1 \
 && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir uv==0.12.13 \
 && uv venv --python /usr/local/bin/python /opt/venv

# Root build context; install common-py as a regular package inside the image.
COPY common-py/pyproject.toml common-py/README.md /opt/referoom-common/
COPY common-py/referoom_common/ /opt/referoom-common/referoom_common/
WORKDIR /app/voice-service
COPY voice-service/requirements.txt ./requirements.txt
RUN sed '/^[[:space:]]*-e[[:space:]]*\.\.\/common-py/d' requirements.txt > /tmp/requirements.txt \
 && uv pip install --no-cache --python /opt/venv/bin/python -r /tmp/requirements.txt /opt/referoom-common \
 && uv pip check --python /opt/venv/bin/python \
 && python -c "import referoom_common, faster_whisper" \
 && rm /tmp/requirements.txt

RUN groupadd --gid 10001 app \
 && useradd --uid 10001 --gid app --create-home app \
 && mkdir -p /app/voice-service/data/audio /app/voice-service/data/tmp /home/app/.cache/huggingface \
 && chown -R app:app /app/voice-service /home/app
COPY --chown=app:app voice-service/app/ ./app/
RUN python -c "from pathlib import Path; import importlib.metadata as m, json; assert not list(Path('/app').rglob('.env*')); assert not list(Path('/opt/referoom-common').rglob('.env*')); assert not json.loads(m.distribution('referoom-common').read_text('direct_url.json')).get('dir_info', {}).get('editable', False)"
USER app
EXPOSE 8008
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8008"]

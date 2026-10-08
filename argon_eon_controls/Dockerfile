FROM python:3.13.7-slim-bookworm
ARG BUILD_VERSION=1.0.2
# Supervisor >= 2026.04 builds with buildx and no longer passes BUILD_FROM; it also injects these labels,
# but they are repeated here so a plain `docker build` produces an identical, recognisable app image.
LABEL io.hass.version="${BUILD_VERSION}" io.hass.type="app" io.hass.arch="aarch64" \
      io.hass.name="Argon EON Controls" io.hass.description="Fan, OLED, temperature and disk controls for the Argon EON case"
RUN apt-get -o Acquire::Retries=5 update && apt-get -o Acquire::Retries=5 install -y --no-install-recommends smartmontools tzdata && rm -rf /var/lib/apt/lists/*
COPY wheels /wheels
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir --no-index --find-links=/wheels --require-hashes -r /requirements.txt
WORKDIR /app
COPY *.py /app/
COPY upstream_argoneon /app/upstream_argoneon
COPY static /app/static
COPY templates /app/templates
COPY tests /app/tests
# Self-test gate: an image whose control logic fails its own tests must not install.
RUN python3 -m unittest discover -s /app/tests -q
CMD ["python3","-u","app.py"]

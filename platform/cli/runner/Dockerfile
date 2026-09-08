FROM python:3.12-slim

# Runner image for Layer-1 checks. Pins are EXACT; the CLI records them in its
# verdict output at build time via `docker run --rm keel-runner:0.1 python -c ...`.
RUN pip install --no-cache-dir \
    pydantic==2.13.4 \
    pytest==9.1.1

WORKDIR /work

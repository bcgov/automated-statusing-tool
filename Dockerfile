FROM python:3.13-slim

# # The installer requires curl (and certificates) to download the release archive
# RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates

# # Download the 0.12.18 installer
# ADD https://astral.sh/uv/0.12.18/install.sh /uv-installer.sh

# # Run the installer, move binary, set permissions, remove installer
# RUN sh /uv-installer.sh && \
#     mv /root/.local/bin/uv /usr/local/bin/uv && \
#     chmod a+rx /usr/local/bin/uv && \
#     rm /uv-installer.sh

# get uv from image
COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /usr/local/bin/uv

# Set the UV to PATH and the CACHE to a all user writable location
ENV UV_CACHE_DIR="/tmp/uv"

COPY . /ast_engine
WORKDIR /ast_engine

# uv add uvicorn tool
RUN uv tool install uvicorn
RUN uv sync --locked

# change ownership for cache
RUN chgrp -R 0 /tmp/uv && \
    chmod -R g+rw /tmp/uv

# run app
# CMD ["uv", "run", "python", "-m", "uvicorn","main:app","--host","0.0.0.0","--port","8000"]
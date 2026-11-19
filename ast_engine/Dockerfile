# /ast_api/Dockerfile
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

# Enable bytecode compilation and copy link mode for caching/performance
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Point UV cache to a writable path in OpenShift
ENV UV_CACHE_DIR=/tmp/uv-cache

# Copy dependency management files
COPY pyproject.toml uv.lock /app/

# Install dependencies
RUN uv sync --frozen --no-install-project --no-dev

# Copy the rest of the application code
COPY ./ast_engine /app

# RUN uv tool install uvicorn
RUN uv sync --frozen --no-dev

# Allow non-root access to uv cache
RUN chgrp -R 0 /app /tmp/uv-cache && \
    chmod -R g+rwX /app /tmp/uv-cache

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

# Expose port and run application
CMD ["uv", "run", "python", "-m" , "ast_engine.entry.redis_worker"]
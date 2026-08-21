FROM python:3.10-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
	PYTHONDONTWRITEBYTECODE=1 \
	UV_PROJECT_ENVIRONMENT="/opt/venv"

RUN apt-get update && apt-get install --no-install-recommends -y curl build-essential git libpq-dev \
	&& apt-get clean \
 	&& rm -rf /var/lib/apt/lists/*

WORKDIR /bot

# uv
RUN pip install --no-cache-dir uv

COPY . .

RUN uv sync --locked

CMD ["uv", "run", "lightning", "docker-run"]
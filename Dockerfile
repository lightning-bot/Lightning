FROM python:3.10-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
	PYTHONDONTWRITEBYTECODE=1 \
	POETRY_HOME="/opt/poetry"

ENV PATH="$POETRY_HOME/bin:$PATH"

RUN apt-get update && apt-get install --no-install-recommends -y curl build-essential git libpq-dev \
	&& apt-get clean \
 	&& rm -rf /var/lib/apt/lists/*

WORKDIR /bot

# Poetry
RUN curl -sSL https://install.python-poetry.org | python -

COPY . .

RUN poetry install --no-ansi

CMD ["poetry", "run", "lightning", "docker-run"]
FROM python:3.13-slim AS builder

RUN apt update && apt upgrade -y

WORKDIR /app/

COPY . .

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

RUN pip install uv
RUN uv sync --locked --no-dev

FROM python:3.13-slim AS runtime

COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app

ARG ENV=production

ENTRYPOINT ["python3", "-O", "main.py"]

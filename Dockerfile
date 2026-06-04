FROM python:3.13-alpine AS builder

RUN apk add gcc git

WORKDIR /app/

COPY . .

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

RUN pip install uv
RUN uv sync --locked --no-dev

FROM python:3.13-alpine AS runtime

COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app

ARG ENV=production

ENTRYPOINT ["python3", "-O", "main.py"]

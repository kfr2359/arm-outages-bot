FROM python:3.13-slim

RUN apt update && apt install -y gcc git

ENV DHOMEDIR=/app

ARG ENV=production

COPY . $DHOMEDIR

WORKDIR $DHOMEDIR
RUN pip install .

ENTRYPOINT ["python3", "main.py"]

FROM python:3.12-slim
LABEL maintainer="dainsleif@yeah.net"
WORKDIR /app

COPY fetch.py .
COPY update.py .
COPY push.py .
COPY requirements.txt .
COPY --chmod=0755 entrypoint.sh /usr/local/bin/
RUN pip install -r requirements.txt && playwright install webkit && playwright install-deps webkit

ENTRYPOINT ["entrypoint.sh"]
VOLUME ["/app/private-key.pem"]

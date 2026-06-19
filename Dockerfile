FROM python:3.12-alpine
LABEL maintainer="dainsleif@yeah.net"
WORKDIR /app

COPY fetch.py .
COPY update.py .
COPY push.py .
COPY requirements.txt .
COPY --chmod=0755 entrypoint.sh /usr/local/bin/
RUN pip install -r requirements.txt && playwright install webkit

ENTRYPOINT ["entrypoint.sh"]
VOLUME ["/app/private-key.pem"]

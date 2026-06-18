FROM node:22-alpine
LABEL maintainer="dainsleif@yeah.net"
WORKDIR /app

COPY fetch.ts .
COPY update.ts .
COPY push.ts .
COPY package.json .
COPY --chmod=0755 entrypoint.sh /usr/local/bin/
RUN npm i --omit=dev

ENTRYPOINT ["entrypoint.sh"]

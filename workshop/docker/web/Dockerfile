FROM node:24-alpine

RUN apk add --no-cache ttyd tmux bash python3 py3-pip tar

WORKDIR /app

COPY workshop/docker/web/start.sh /start.sh
COPY workshop/docker/web/tmux.conf /etc/tmux.conf
RUN chmod +x /start.sh

EXPOSE 3000 7681

CMD ["/start.sh"]

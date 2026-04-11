# syntax=docker/dockerfile:1
FROM python:3.14-slim-bookworm

RUN    apt update \
    && apt upgrade -y

# Remove me after development
RUN    apt install -y  openssh-server

RUN    apt install -y \
         bash \
         vim \
         plc-utils \
         plc-utils-extra \
         mosquitto-clients \
         procps \
    && rm -rf /var/lib/apt/lists/*

# upgrade pip to avoid warnings during the docker build
RUN     pip install --root-user-action=ignore --upgrade pip \
    &&  pip install --root-user-action=ignore --no-cache-dir paho-mqtt \
    &&  pip install --root-user-action=ignore --no-cache-dir pyyaml jsons

WORKDIR /app

COPY powerlineStat2mqtt.py ./
COPY powerlineStat2mqtt powerlineStat2mqtt/

# Force invalidating the cache before git clone
ARG BUILD_DATE=-1
RUN echo "$BUILD_DATE"

RUN git clone --branch main https://github.com/HaraldR42/powerlineStat2mqtt.git .

ENTRYPOINT [ "python3", "-u", "./powerlineStat2mqtt.py", "--config", "/app/conf/powerlineStat2mqtt.conf.yaml" ]

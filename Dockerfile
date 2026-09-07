# syntax=docker/dockerfile:1
FROM python:3.14-slim-trixie

RUN    sed -i -e's/ main/ main contrib non-free/g' /etc/apt/sources.list.d/debian.sources \
    && apt update \
    && apt dist-upgrade -y

# Pre-downloaded pla-util package to avoid downloading it from the internet during the docker build
#COPY pla-util/pla-util_2.1.3-1+2.7_amd64.deb /tmp/

RUN    apt install -y \
         bash \
         vim \
         git \
         plc-utils \
         plc-utils-extra \
         procps \
    && apt install -y /tmp/pla-util_2.1.3-1+2.7_amd64.deb \
    && rm -rf /var/lib/apt/lists/* \
    && rm /tmp/pla-util_2.1.3-1+2.7_amd64.deb

# upgrade pip to avoid warnings during the docker build
RUN     pip install --root-user-action=ignore --upgrade pip \
    &&  pip install --root-user-action=ignore --no-cache-dir paho-mqtt \
    &&  pip install --root-user-action=ignore --no-cache-dir pyyaml jsons

WORKDIR /app

# Force invalidating the cache before copy
ARG BUILD_DATE=-1
RUN echo "$BUILD_DATE"

COPY powerlineStat2mqtt.py ./
COPY powerlineStat2mqtt powerlineStat2mqtt/

ENTRYPOINT [ "python3", "-u", "./powerlineStat2mqtt.py", "--config", "/app/conf/powerlineStat2mqtt.conf.yaml" ]

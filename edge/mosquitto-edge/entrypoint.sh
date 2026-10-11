#!/bin/sh
set -e

FOG_HOST="${FOG_HOST:-localhost}"
CONFIG_SRC="/mosquitto/config/mosquitto.conf.tpl"
CONFIG_DST="/mosquitto/config/mosquitto.conf"

echo "[entrypoint] Rendering mosquitto config: FOG_HOST=${FOG_HOST}"
sed "s/@FOG_HOST@/${FOG_HOST}/g" "${CONFIG_SRC}" > "${CONFIG_DST}"

exec mosquitto -c "${CONFIG_DST}"

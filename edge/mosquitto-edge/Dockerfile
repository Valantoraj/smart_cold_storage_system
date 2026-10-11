FROM eclipse-mosquitto:2.0.20

COPY mosquitto.conf.tpl /mosquitto/config/mosquitto.conf.tpl
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 1883

ENTRYPOINT ["/entrypoint.sh"]

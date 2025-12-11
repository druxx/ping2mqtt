# ping2mqtt - Sent availibilty and latency information to mqtt.

This program is heavily inspired by https://github.com/skullydazed/ping2mqtt but the use case is a little bit different: 
This program will continuously ping one or more hosts and send a message as soon as a host turns alive and sent a message when it stops replying. Statistics is sent as well. It also publishes Home Assistant MQTT autodiscovery information.

# Running

Use docker to launch this. A typical invocation is:

# Configuration


| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | | Set to `1` to enable additional debug logging. |
| `HOMEASSISTANT_PREFIX` | `homeassistant` | The prefix for Home Assistant discovery. Must be the same as `discovery_prefix` in your Home Assistant configuration. |
| `HOSTLIST` | | A comma separated list of hosts to ping. Each entry: `<hostname[:ip_address][:ping_interval_in_secs>` The default ping interval is 1sec|
| `MQTT_CLIENT_ID` | `ping2mqtt` | The client id to send to the MQTT broker. |
| `MQTT_USER` |  | The user to send to the MQTT broker. Leave unset to disable authentication. |
| `MQTT_PASSWD` |  | The password to send to the MQTT broker. Leave unset to disable authentication. |
| `MQTT_HOST` | `localhost` | The MQTT broker to connect to. |
| `MQTT_PORT` | `1883` | The port on the broker to connect to. |
| `MQTT_TIMEOUT` | `60` | The timeout for the MQTT connection. |
| `MQTT_TOPIC_PREFIX` | `ping` | The MQTT topic prefix. With the default data will be published to `ping/<hostname>`. |
| `MQTT_QOS` | `1` | The MQTT QOS level |

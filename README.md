# ping2mqtt - Sent availibilty and latency information to mqtt.

This program is heavily inspired by https://github.com/skullydazed/ping2mqtt but the use case is a little bit different: 
This program will continuously ping one or more hosts and send a message as soon as a host turns alive and sent a message when it stops replying. Statistics is sent as well. It also publishes Home Assistant MQTT autodiscovery information.

# Running

Use docker to launch this. A typical invocation is:

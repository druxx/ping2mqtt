#!/usr/bin/env python3
"""Script to ping hosts and sent status to MQTT.
"""
import asyncio
import atexit
import json
import time
from os import environ
from socket import gethostbyname

import aioping
import paho.mqtt.client

DEBUG = environ.get('DEBUG') == '1'
HOMEASSISTANT_PREFIX = environ.get('HOMEASSISTANT_PREFIX', 'homeassistant')
HOSTLIST = environ.get('HOSTLIST', 'localhost:127.0.0.1')
MQTT_CLIENT_ID = environ.get('MQTT_CLIENT_ID', 'ping2mqtt')
MQTT_USER = environ.get('MQTT_USER', '')
MQTT_PASSWD = environ.get('MQTT_PASSWD', '')
MQTT_HOST = environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(environ.get('MQTT_PORT', '1883'))
MQTT_TOPIC_PREFIX = environ.get('MQTT_TOPIC_PREFIX', 'ping')
MQTT_QOS = int(environ.get('MQTT_QOS', 1))
MQTT_TIMEOUT = int(environ.get('MQTT_TIMEOUT', 60))

REPORT_INTERVAL = int(environ.get('REPORT_INTERVAL', '60'))  # seconds

hostlist = {}

for host in HOSTLIST.split(','):
    if ':' in host:
        hostname, ip = host.strip().split(':')
    else:
        hostname = host
        if DEBUG:
            print(f'Looking up IP for {host}')
        ip = gethostbyname(host)
        if DEBUG:
            print(f'Found IP {ip} for {host}')

    hostlist[ip] = {
        'interval': 1, # ping interval in seconds
        'name': hostname,
        'ip': ip,
        'alive': None,
        'last_1_min': [],
        'last_5_min': [],
        'latency': {}
    }

lock = asyncio.Lock()
mqtt = paho.mqtt.client.Client()

def mqtt_disconnect():
    mqtt.disconnect()
    mqtt.loop_stop()


def mqtt_send(topic, payload, retain=False):
    try:
        if DEBUG:
            print(f'Sending to MQTT: {topic}: {payload}')
        mqtt.publish(topic, payload=payload, qos=MQTT_QOS, retain=retain)
    except Exception as e:
        print(f'MQTT Publish Failed: {e}')

#  "unit_of_measurement": "hPa",
#  "suggested_display_precision": 0

def getDiscoveryHostname(hostname):
    """Return Home Assistant discovery hostname for a host.
    """
    return hostname.replace('.', '_').replace(' ', '_')

def getHADeviceIdentifier(hostname):
    """Return Home Assistant device identifier for a host.
    """
    return f"{MQTT_TOPIC_PREFIX.title()}_{getDiscoveryHostname(hostname)}".lower()


def getHADeviceInfo(hostname):
    """Return Home Assistant device info dictionary for a host.
    """
    return {
        'identifiers': getHADeviceIdentifier(hostname),
        'name': f"{MQTT_TOPIC_PREFIX.title()} {hostname}",
        'model': 'ping2mqtt',
        'manufacturer': 'Custom Script'
    }   

def getDefaultRegistrationPacket(hostname, sensor='alive'):
    """Return default Home Assistant registration packet for a host.
    """
    return {
        'device': getHADeviceInfo(hostname),
        'unique_id': getHADeviceIdentifier(hostname) + f'_{sensor}',
        'object_id': getHADeviceIdentifier(hostname) + f'_{sensor}',
        'availability_topic': 'ping/status',
        'payload_available': 'online',
        'payload_not_available': 'offline',
        'state_topic': f'{MQTT_TOPIC_PREFIX}/' + getDiscoveryHostname(hostname),
#        'device_class': 'connectivity'
#        'json_attributes_topic': f'{MQTT_TOPIC_PREFIX}/{hostname}',
    }

def send_homeassistant_registration(hostname):
    """Register an MQTT device for a host.
    """
    entities = { 'alive': {'type': 'binary_sensor' }, \
        'count': { 'type': 'sensor' }, \
        'min': { 'type': 'sensor', 'unit': 'msec' }, \
        'avg': { 'type': 'sensor', 'unit': 'msec' }, \
        'max': { 'type': 'sensor', 'unit': 'msec' }, \
        'percent_dropped': { 'type': 'sensor', 'unit': '%' } }

    for key, typeUnit in entities.items():
        registration_packet = getDefaultRegistrationPacket(hostname, sensor=key)
        registration_packet['value_template'] = f'{{{{ value_json.{key} }}}}'
        if 'unit' in typeUnit:
            registration_packet['unit_of_measurement'] = typeUnit['unit']
        registration_packet['value_template'] = f'{{{{ value_json.{key} }}}}'
        registration_topic = HOMEASSISTANT_PREFIX + '/{}/{}/{}/config'.format(typeUnit['type'], getHADeviceIdentifier(hostname), key)
#        print(key, registration_packet)
        mqtt_send(registration_topic, json.dumps(registration_packet), retain=True)



def update_statistics(stat,delay):
    """Update statistics dictionary with new delay value.
    """
    stat['count'] += 1
    stat['sum'] += delay
    if delay < stat['min']:
        stat['min'] = delay
    if delay > stat['max']:
        stat['max'] = delay



async def pinger(host):
    alive = False
    stat = {'count': 0, 'sum': 0, 'min': 9999, 'max': 0, 'lost': 0}
    previous_report_time = 0
    while True:
        start = time.time()
        aliveNow = False
        try:
            delay = await aioping.ping(host['ip'], timeout=host['interval'])  # timeout in seconds
            aliveNow = True
            update_statistics(stat, delay*1000)
        except TimeoutError:
            stat['lost'] += 1
            stat['count'] += 1
        if aliveNow != alive:
            async with lock:
                mqtt_send(f'{MQTT_TOPIC_PREFIX}/{host["name"]}', json.dumps({'alive': aliveNow}))
            alive = aliveNow
        sleep = start + host['interval'] - time.time()
        if time.time() - previous_report_time >= REPORT_INTERVAL:
            async with lock:
                mqtt_send(f'{MQTT_TOPIC_PREFIX}/{host["name"]}', json.dumps({
                    'alive': alive,
                    'latency': {
                        'count': stat['count'],
                        'min': stat['min'],
                        'avg': stat['sum'] / stat['count'] if stat['count'] > 0 else None,
                        'max': stat['max'],
                        'percent_dropped': (stat['lost'] / stat['count'] * 100) if stat['count'] > 0 else 100
                    }
                }))
            previous_report_time = time.time()
            stat = {'count': 0, 'sum': 0, 'min': 9999, 'max': 0, 'lost': 0}
        await asyncio.sleep(sleep if sleep > 0 else 0)
        
        
async def main():
    tasks = []
    for host in hostlist.values():
        t = asyncio.create_task(pinger(host))
        tasks.append(t)

    # keep the program alive forever
    await asyncio.gather(*tasks)

if __name__ == '__main__':
    # Start the MQTT thread
    mqtt.username_pw_set(username=MQTT_USER,password=MQTT_PASSWD)
    mqtt.will_set("ping/status", "offline", qos=MQTT_QOS, retain=True)
    mqtt.connect(MQTT_HOST, MQTT_PORT, MQTT_TIMEOUT)
    mqtt.publish('ping/status', 'online', qos=MQTT_QOS, retain=True)
    mqtt.loop_start()
    print('Connected to MQTT broker')
    atexit.register(mqtt_disconnect)

    # Register hosts with HA
    for host in hostlist.values():
        send_homeassistant_registration(host['name'])

    asyncio.run(main())



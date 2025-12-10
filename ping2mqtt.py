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
DISCOVERY_TOPIC = HOMEASSISTANT_PREFIX + '/binary_sensor/ping/{}/config'

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


def send_homeassistant_registration(hostname):
    """Register an MQTT binary sensor for a host.
    """
    discovery_hostname = hostname.replace('.', '_').replace(' ', '_')
    registration_topic = DISCOVERY_TOPIC.format(discovery_hostname)
    registration_packet = {
        'name': f"{MQTT_TOPIC_PREFIX.title()} {hostname}",
        'unique_id': f'{MQTT_TOPIC_PREFIX}_{registration_topic}',
        'availability_topic': 'ping/status',
        'payload_available': 'online',
        'payload_not_available': 'offline',
        'state_topic': f'{MQTT_TOPIC_PREFIX}/{hostname}',
        'value_template': '{{ value_json.alive }}',
        'payload_on': 'on',
        'payload_off': 'off',
        'device_class': 'connectivity',
        'json_attributes_topic': f'{MQTT_TOPIC_PREFIX}/{hostname}',
    }
    print(f'Registering {hostname} with Home Assistant: {registration_topic}: {registration_packet}')
    mqtt_send(registration_topic, json.dumps(registration_packet), retain=True)


def update_last_mins(host, hostresult):
    """Updates the last 1/5 min datasets.
    """
    if len(host['last_1_min']) >= 6:
        del(host['last_1_min'][0])
    host['last_1_min'].append({'min': hostresult.min_rtt, 'avg': hostresult.avg_rtt, 'max': hostresult.max_rtt, 'sent': hostresult.packets_sent, 'received': hostresult.packets_received})

    if len(host['last_5_min']) >= 30:
        del(host['last_5_min'][0])
    host['last_5_min'].append({'min': hostresult.min_rtt, 'avg': hostresult.avg_rtt, 'max': hostresult.max_rtt, 'sent': hostresult.packets_sent, 'received': hostresult.packets_received})

    host['latency'] = {
        'alive': 'on' if host['alive'] else 'off',
        'last_10_sec': min_avg_max([host['last_1_min'][-1]]),
        'last_1_min': min_avg_max(host['last_1_min']),
        'last_5_min': min_avg_max(host['last_5_min'])
    }


def min_avg_max(dataset):
    """Takes a sequence of min,avg,max dictionaries and finds the min,avg,max of the set.
    """
    result = {
        'min': None, 
        'avg': None, 
        'max': None,
        'percent_dropped': None
    }
    avg_sum = 0
    sent = 0
    received = 0

    for datapoint in dataset:
        if not result['min'] or datapoint['min'] < result['min']:
            result['min'] = datapoint['min']

        if not result['max'] or datapoint['max'] > result['max']:
            result['max'] = datapoint['max']

        avg_sum += datapoint['avg']
        sent += datapoint['sent']
        received += datapoint['received']

    result['avg'] = avg_sum / len(dataset)
    if received == 0:
        result['percent_dropped'] = 100
    else:
        result['percent_dropped'] = 100 - (received / sent * 100)

    return result



async def pinger(host):
    alive = False
    lost = 0
    max = 0
    min = 9999
    while True:
        start = time.time()
        aliveNow = False
        try:
            delay = await aioping.ping(host['ip'], timeout=host['interval'], count=1)  # timeout in seconds
            aliveNow = True
        except TimeoutError:
            lost += 1
        if aliveNow != alive:
            async with lock:
                mqtt_send(f'{MQTT_TOPIC_PREFIX}/{host["name"]}', json.dumps({'alive': aliveNow}))
            alive = aliveNow
        sleep = start + host['interval'] - time.time()
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
    atexit.register(mqtt_disconnect)

    # Register hosts with HA
    for host in hostlist.values():
        send_homeassistant_registration(host['name'])

    asyncio.run(main())

#    while True:
#        # Ping forever
#        try:
#            hostresults = multiping(hostlist, count=10, timeout=1)
#            for hostresult in hostresults:
#                host = hostlist[hostresult.address]
#                host['alive'] = hostresult.is_alive
#                update_last_mins(host, hostresult)
#                #print(f'Sending to MQTT: {MQTT_TOPIC_PREFIX}/{host["name"]} {json.dumps(host["latency"])}')
#                mqtt_send(f'{MQTT_TOPIC_PREFIX}/{host["name"]}', json.dumps(host["latency"]))
#                #pprint(hostlist)

#        except Exception as e:
#            print(f'Uncaught exception: {e.__class__.__name__}: {e}')
#            print_exc()

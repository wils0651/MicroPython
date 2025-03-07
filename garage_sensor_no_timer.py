from machine import Pin, Timer, WDT
from time import sleep
import network
import sys
from umqtt.simple import MQTTClient
import config
from hcsr04 import HCSR04

led = Pin("LED", Pin.OUT)

triggerPin = 5
echoPin = 4
hcsr = HCSR04(triggerPin, echoPin)

measurements = []

# MQTT Parameters
MQTT_SERVER = config.mqtt_server
MQTT_PORT = 0
MQTT_USER = config.mqtt_username
MQTT_PASSWORD = config.mqtt_password
MQTT_CLIENT_ID = b"garage_picow"
MQTT_KEEPALIVE = 7200
MQTT_SSL = False   # set to False if using local MQTT broker

MQTT_TOPIC = 'garage_sensor'

THRESHOLD = 10 # cm

def initialize_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    network.hostname(MQTT_CLIENT_ID)
    wlan.active(True)
    
    led.value(1)

    # Connect to the network
    wlan.connect(ssid, password)

    # Wait for Wi-Fi connection
    connection_timeout = 10
    while connection_timeout > 0:
        if wlan.status() >= 3:
            break
        connection_timeout -= 1
        print('Acquiring Wi-Fi connection...')
        sleep(1)

    # Check if connection is successful
    if wlan.status() != 3:
        return False
    else:
        print('Connection successful!')
        network_info = wlan.ifconfig()
        print('IP address:', network_info[0])
        led.value(0)
        return True
    
def connect_mqtt():
    try:
        client = MQTTClient(client_id=MQTT_CLIENT_ID,
                            server=MQTT_SERVER,
                            port=MQTT_PORT,
                            user=MQTT_USER,
                            password=MQTT_PASSWORD,
                            keepalive=MQTT_KEEPALIVE,
                            ssl=MQTT_SSL)
        client.connect()
        return client
    except Exception as e:
        print('Error connecting to MQTT:', e)
        raise  # Re-raise the exception to see the full traceback

def publish_mqtt(topic, value):
    client.publish(topic, value)
    print(topic)
    print(value)
    print("Published")

def should_publish(dist):
    if len(measurements) < 5:
        return False
    
    mean_distance = sum(measurements) / len(measurements)
    distance_diff = abs(dist - mean_distance)
    return distance_diff > THRESHOLD or len(measurements) >= 240


def measure_and_publish():
    distance = hcsr.distance_cm()
    print(distance)

    if should_publish(distance):
        message = f"{distance:.2f}"
        measurements.clear()
        publish_mqtt(MQTT_TOPIC, message)

    measurements.append(distance)

    
def restart():
    network.WLAN().active(False)
    print('Restart in 60 seconds')
    sleep(60)
    print('Restarting Pico')
    led.value(0)
    sys.exit()

try:
    if not initialize_wifi(config.wifi_ssid, config.wifi_password):
        print('Error connecting to the network. exiting program')
        restart()
    else:
        client = connect_mqtt()
        while True:
            measure_and_publish()
            sleep(1)
            
except Exception as e:
    print('Error:', e)
    restart()
    





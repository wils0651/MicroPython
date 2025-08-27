from machine import Pin, Timer, WDT
from time import sleep
import network
import sys
from umqtt.simple import MQTTClient
import config

led = Pin("LED", Pin.OUT)

# MQTT Parameters
MQTT_SERVER = config.mqtt_server
MQTT_PORT = 0
MQTT_USER = config.mqtt_username
MQTT_PASSWORD = config.mqtt_password
MQTT_CLIENT_ID = b"garage_picow2"
MQTT_KEEPALIVE = 7200
MQTT_SSL = False   # set to False if using local MQTT broker

MQTT_TOPIC = 'garage_sensor'

def enum(**enums: int):
    return type('Enum', (), enums)

GarageState = enum(DOOR_OPEN=1, CAR_INSIDE=2, GARAGE_EMPTY=3, UNKNOWN=4)


def initialize_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
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
        client.set_callback(process_message)
        client.connect()
        return client
    except Exception as e:
        print('Error connecting to MQTT:', e)
        raise  # Re-raise the exception to see the full traceback

def process_message(topic, message):
    print('Topic:', topic)
    print('Message:', message)
    # check for message
    # parse message
    # set led based on garage state

def parse_message(message):
    print('Message:', message)


def restart():
    print('Restart in 60 seconds')
    network.WLAN().active(False)
    sleep(60)
    print('Restarting Pico')
    led.value(0)
    sys.exit()

try:
    if not initialize_wifi(config.wifi_ssid, config.wifi_password):
        print('Error connecting to the network. exiting program')
        restart()
    else:
        # Connect to MQTT broker, start MQTT client
        client = connect_mqtt()
        client.subscribe(MQTT_TOPIC)
        print("subscribed")
        while True:
            client.check_msg()
            # print("waited msg")
            
except Exception as e:
    print('Error:', e)
    restart()





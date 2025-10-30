from machine import Pin, Timer, WDT
#from time import sleep
import time
import network
import sys
from umqtt.simple import MQTTClient
import config

onboard_led = Pin("LED", Pin.OUT)

# MQTT Parameters
MQTT_SERVER = config.mqtt_server
MQTT_PORT = 0
MQTT_USER = config.mqtt_username
MQTT_PASSWORD = config.mqtt_password
MQTT_CLIENT_ID = b"garage_picow2b"
MQTT_KEEPALIVE = 7200
MQTT_SSL = False   # set to False if using local MQTT broker

MQTT_TOPIC = 'garage_sensor'

# Garage Distance Ranges (in cm)
OPEN_RANGE_UPPER = 40
OPEN_RANGE_LOWER = 15

LAST_MESSAGE_TIMEOUT = 600  # 10 minutes
TIME_BETWEEN_ACTIVE_BLINKS = 20  # seconds
ACTIVE_BLINK_TIME = 1 # second

# LED Pin Definitions
OPEN_LED_PIN = 15
ERROR_LED_PIN = 14
ACTIVE_LED_PIN = 13

open_led = Pin(OPEN_LED_PIN, Pin.OUT)
error_led = Pin(ERROR_LED_PIN, Pin.OUT)
active_led = Pin(ACTIVE_LED_PIN, Pin.OUT)

open_led_on = False
error_led_on = False
active_led_on = False

last_message_time = 0.0
last_active_blink_time = 0.0

def initialize_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    onboard_led.value(1)
    active_led.value(1)

    # Connect to the network
    wlan.connect(ssid, password)

    # Wait for Wi-Fi connection
    connection_timeout = 10
    while connection_timeout > 0:
        if wlan.status() >= 3:
            break
        connection_timeout -= 1
        print('Acquiring Wi-Fi connection...')
        time.sleep(1)

    # Check if connection is successful
    if wlan.status() != 3:
        return False
    else:
        print('Connection successful!')
        network_info = wlan.ifconfig()
        print('IP address:', network_info[0])
        onboard_led.value(0)
        active_led.value(0)
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
    # use a regular expression to remove non-numeric characters
    message = message.decode('utf-8').strip()

    # parse message
    distance = parse_message(message)
    print('Distance:', distance)
    # set led based on garage state
    set_open_led(distance)
    # update last message time
    set_last_message_time()

def parse_message(message):
    if(message is None):
        print('No message received')
        return -1
    
    print('Parsing Message:', message)

    try:
        distance = float(message)
        return distance
    except ValueError:
        print('Invalid message format')
        return -1

def set_open_led(distance):
    global open_led_on
    if OPEN_RANGE_LOWER <= distance <= OPEN_RANGE_UPPER:
        if not open_led_on:
            reset_leds()
            open_led.value(1)
            open_led_on = True
            print('Garage is OPEN - Open LED ON')
    else:
        if open_led_on:
            open_led.value(0)
            open_led_on = False
            print('Garage is CLOSED - Open LED OFF')

def reset_leds():
    global open_led_on, error_led_on, active_led_on
    open_led.value(0)
    error_led.value(0)
    active_led.value(0)
    onboard_led.value(0)
    open_led_on = False
    error_led_on = False
    active_led_on = False            

def set_last_message_time():
    global last_message_time
    last_message_time = time.time()

def check_last_message_timeout():
    global last_message_time, error_led_on
    current_time = time.time()
    if (current_time - last_message_time) > LAST_MESSAGE_TIMEOUT:
        print('current_time:', current_time)
        print('last_message_time:', last_message_time)
        print('No message received in the last', LAST_MESSAGE_TIMEOUT, 'seconds')
        error_led.value(1)
        error_led_on = True


def check_active_blink():
    global last_active_blink_time, active_led_on, error_led_on
    if error_led_on:
        return
    
    current_time = time.time()
    time_since_last_blink = current_time - last_active_blink_time
    if active_led_on and time_since_last_blink >= TIME_BETWEEN_ACTIVE_BLINKS + ACTIVE_BLINK_TIME:
        active_led.value(0)
        active_led_on = False
        last_active_blink_time = current_time
    elif (current_time - last_active_blink_time) >= TIME_BETWEEN_ACTIVE_BLINKS:
        active_led.value(1)
        active_led_on = True        

def restart():
    error_led.value(1)
    print('Restart in 60 seconds')
    network.WLAN().active(False)
    time.sleep(60)
    print('Restarting Pico')
    reset_leds()
    set_last_message_time()
    sys.exit()

try:
    set_last_message_time()
    reset_leds()
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
            check_active_blink()
            check_last_message_timeout()
            
except Exception as e:
    print('Error:', e)
    restart()





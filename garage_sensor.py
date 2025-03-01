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

measure_timer = Timer()
led_timer = Timer()
watchdog_timer = Timer()
watchdog = WDT(timeout=8300) 


# MQTT Parameters
MQTT_SERVER = config.mqtt_server
MQTT_PORT = 0
MQTT_USER = config.mqtt_username
MQTT_PASSWORD = config.mqtt_password
MQTT_CLIENT_ID = b"garage_picow"
MQTT_KEEPALIVE = 7200
MQTT_SSL = False   # set to False if using local MQTT broker

MQTT_TOPIC = 'garage_sensor'

garage_door_distance = 40
car_distance = 80
floor_distance = 250
threshold = 10

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
        watchdog.feed()
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

def get_garage_status(distance):
    if abs(distance - garage_door_distance) < threshold:
        return GarageState.DOOR_OPEN
    elif abs(distance - car_distance) < threshold:
        return GarageState.CAR_INSIDE
    elif abs(distance - floor_distance) < threshold:
        return GarageState.GARAGE_EMPTY
    else:
        return GarageState.UNKNOWN

def get_garage_message(garage_state):
    if garage_state == GarageState.DOOR_OPEN:
        return "garage_open"
    elif garage_state == GarageState.CAR_INSIDE:
        return "car_inside"
    elif garage_state == GarageState.GARAGE_EMPTY:
        return "garage_empty"
    elif garage_state == GarageState.UNKNOWN:
        return "garage_unknown"
    else:
        return "error"

def measure_and_publish(timer):
    distance = hcsr.distance_cm()
    garage_state = get_garage_status(distance)
    garage_state_message = get_garage_message(garage_state)
    message = f"{garage_state_message} {distance:.2f}"

    # Publish as MQTT payload
    publish_mqtt(MQTT_TOPIC, message)
    blink_led()
    
def led_off(timer):
    led.value(0)
    
def led_toggle(timer):
    watchdog.feed() 
    led.toggle()
    
def blink_led():
    led.value(1)
    led_timer.init(period=500, mode=Timer.ONE_SHOT, callback=led_off)
    
def error_led():
    led_timer.init(period=500, mode=Timer.PERIODIC, callback=led_toggle)

def watchdog_feed(timer):
    watchdog.feed()    

def restart():
    print('Restart in 60 seconds')
    measure_timer.deinit()
    sleep(60)
    print('Restarting Pico')
    watchdog_timer.deinit()
    led_timer.deinit()
    led.value(0)
    sys.exit()

try:
    if not initialize_wifi(config.wifi_ssid, config.wifi_password):
        print('Error connecting to the network. exiting program')
        error_led()
        restart()
    else:
        # Connect to MQTT broker, start MQTT client
        client = connect_mqtt()
        watchdog_timer.init(period=5000, mode=Timer.PERIODIC, callback=watchdog_feed)
        measure_timer.init(period=90000, mode=Timer.PERIODIC, callback=measure_and_publish)
            
except Exception as e:
    error_led()
    print('Error:', e)
    restart()
    




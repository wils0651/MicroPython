from machine import Pin, I2C, Timer, WDT
import time
import network
import sys
from umqtt.simple import MQTTClient
import config
from libraries.mcp9808 import MCP9808
from collections import deque

# MQTT Parameters
MQTT_SERVER = config.mqtt_server
MQTT_PORT = 0
MQTT_USER = config.mqtt_username
MQTT_PASSWORD = config.mqtt_password
MQTT_CLIENT_ID = b"raspberrypi_picow"
MQTT_KEEPALIVE = 7200
MQTT_SSL = False   # set to False if using local MQTT broker
MQTT_SSL_PARAMS = {'server_hostname': MQTT_SERVER}

MQTT_TOPIC = 'esp8266_DHT'

led = Pin("LED", Pin.OUT)

# Initialize I2C communication
i2c = I2C(id=0, scl=Pin(5), sda=Pin(4), freq=10000)

# create an instance of the sensor, giving it a reference to the I2C bus
mcp = MCP9808(i2c)

measure_timer = Timer()
led_timer = Timer()
watchdog_timer = Timer()
watchdog = WDT(timeout=8300) 

lastTempData = deque((),6)
startTime = time.ticks_ms()

def initialize_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    led.value(1)

    # Connect to the network
    wlan.connect(ssid, password)

    # Wait for Wi-Fi connection
    connection_attempts = 10
    while connection_attempts > 0:
        if wlan.status() >= 3:
            break
        connection_attempts -= 1
        print(f"Connecting to Wi-Fi. Attempts remaining: {connection_attempts}")
        watchdog.feed()
        time.sleep(1)

    # Check if connection is successful
    if wlan.status() != 3:
        wlan.active(False)
        return False
    else:
        print('Connected to WiFi')
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
                            ssl=MQTT_SSL,
                            ssl_params=MQTT_SSL_PARAMS)
        client.connect()
        return client
    except Exception as e:
        print('Error connecting to MQTT:', e)
        raise  # Re-raise the exception to see the full traceback

def publish_mqtt(topic, value):
    led.value(1)
    message = 'probe_3: ' + value
    client.publish(topic, message)
    print(topic)
    print(message)
    print("Publish Done")
    led.value(0)

def get_mean_temp():
    return sum(lastTempData) / len(lastTempData)

def get_std_dev():
    mean = get_mean_temp()
    variance = sum([((x - mean) ** 2) for x in lastTempData]) / len(lastTempData)
    return variance ** 0.5

def should_publish(temperature):
    if(len(lastTempData) < 6):
        return True
    elif time.ticks_diff(time.ticks_ms(), startTime) > 60000 and abs(temperature - get_mean_temp()) > 2 * get_std_dev():
        return True
    elif time.ticks_diff(time.ticks_ms(), startTime) > 120000 and abs(temperature - get_mean_temp()) > get_std_dev():
        return True
    elif time.ticks_diff(time.ticks_ms(), startTime) > 240000:
        return True
    else:
        return False

def measure_and_publish(timer):
    temperature_in_C = mcp.get_temp()
    temperature = (temperature_in_C * 9/5) + 32
    print(f'Temp in F: {temperature}')

    if should_publish(temperature):
        publish_mqtt(MQTT_TOPIC, str(temperature))

    lastTempData.append(temperature)
    global startTime
    startTime = time.ticks_us()

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
    time.sleep(60)
    print('Restarting Pico')
    led_timer.deinit()
    led.value(0)
    sys.exit()

try:
    if not initialize_wifi(config.wifi_ssid, config.wifi_password):
        print('Error connecting to WiFi... exiting program')
        error_led()
        restart()
    else:
        client = connect_mqtt()
        watchdog_timer.init(period=5000, mode=Timer.PERIODIC, callback=watchdog_feed)
        measure_timer.init(period=90000, mode=Timer.PERIODIC, callback=measure_and_publish)

except Exception as e:
    error_led()
    print('Error:', e)
    restart()




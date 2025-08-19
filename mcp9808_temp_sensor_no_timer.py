from machine import Pin, I2C
import time
import network
import sys
from umqtt.simple import MQTTClient
import config
from libraries.mcp9808 import MCP9808

# MQTT Parameters
MQTT_SERVER = config.mqtt_server
MQTT_PORT = 0
MQTT_USER = config.mqtt_username
MQTT_PASSWORD = config.mqtt_password
MQTT_CLIENT_ID = b"raspberrypi_pico"
MQTT_KEEPALIVE = 7200
MQTT_SSL = False   # set to False if using local MQTT broker
MQTT_SSL_PARAMS = {'server_hostname': MQTT_SERVER}

MQTT_TOPIC = config.mqtt_topic
PROBE_ID = config.probe_id

led = Pin("LED", Pin.OUT)

# Initialize I2C communication
i2c = I2C(id=0, scl=Pin(5), sda=Pin(4), freq=10000)

# create an instance of the sensor, giving it a reference to the I2C bus
mcp = MCP9808(i2c)

lastTempData = []

def initialize_wifi(ssid, password):
    network.hostname(PROBE_ID)
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
    message = PROBE_ID + ': ' + value
    client.publish(topic, message)
    print(topic)
    print(message)
    print("Publish Done")
    led.value(0)

def get_mean_temp():
    return sum(lastTempData) / len(lastTempData)

def measure_and_publish():
    temperature_in_C = mcp.get_temp()
    temperature = (temperature_in_C * 9/5) + 32
    print(f'Temp in F: {temperature}')
    lastTempData.append(temperature)

    if len(lastTempData) >= 20:
        meanTemperature = get_mean_temp()
        publish_mqtt(MQTT_TOPIC, str(meanTemperature))
        lastTempData.clear()


def restart():
    print('Restart in 60 seconds')
    time.sleep(60)
    print('Restarting Pico')
    led.value(0)
    sys.exit()

try:
    if not initialize_wifi(config.wifi_ssid, config.wifi_password):
        print('Error connecting to WiFi... exiting program')
        led.value(1)
        restart()
    else:
        client = connect_mqtt()
        while True:
            measure_and_publish()
            time.sleep(3)

except Exception as e:
    led.value(1)
    print('Error:', e)
    restart()





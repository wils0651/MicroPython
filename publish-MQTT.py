from machine import Pin, I2C
from time import sleep
import network
from umqtt.simple import MQTTClient
import config
from libraries.mcp9808 import MCP9808

# MQTT Parameters
MQTT_SERVER = config.mqtt_server
MQTT_PORT = 0
MQTT_USER = config.mqtt_username
MQTT_PASSWORD = config.mqtt_password
MQTT_CLIENT_ID = b"raspberrypi_picow"
MQTT_KEEPALIVE = 7200
MQTT_SSL = False   # set to False if using local Mosquitto MQTT broker
MQTT_SSL_PARAMS = {'server_hostname': MQTT_SERVER}

MQTT_TOPIC = 'esp8266_DHT'

led = Pin("LED", Pin.OUT)

# Initialize I2C communication
i2c = I2C(id=0, scl=Pin(5), sda=Pin(4), freq=10000)

# create an instance of the sensor, giving it a reference to the I2C bus
mcp = MCP9808(i2c)

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
        print('Waiting for Wi-Fi connection...')
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
                            ssl=MQTT_SSL,
                            ssl_params=MQTT_SSL_PARAMS)
        client.connect()
        return client
    except Exception as e:
        print('Error connecting to MQTT:', e)
        raise  # Re-raise the exception to see the full traceback

def publish_mqtt(topic, value):
    client.publish(topic, value)
    print(topic)
    print(value)
    print("Publish Done")

try:
    if not initialize_wifi(config.wifi_ssid, config.wifi_password):
        print('Error connecting to the network... exiting program')
    else:
        # Connect to MQTT broker, start MQTT client
        client = connect_mqtt()
        while True:
            # Read sensor data
            temperature = mcp.get_temp()
            print(temperature)

            # Publish as MQTT payload
            publish_mqtt(MQTT_TOPIC, str(temperature))
            
            # Delay 90 seconds
            sleep(90)

except Exception as e:
    print('Error:', e)


from machine import Pin, I2C, Timer
from time import sleep
from libraries.mcp9808 import MCP9808

led = Pin("LED", Pin.OUT)

# Initialize I2C communication
i2c = I2C(id=0, scl=Pin(5), sda=Pin(4), freq=10000)
print(i2c.scan())

# create an instance of the sensor, giving it a reference to the I2C bus
mcp = MCP9808(i2c)

tim = Timer()

def tick(timer):
    global led
    led.toggle()
    # get the temperature (float)
    temp_celsius = mcp.get_temp()
    print(temp_celsius)


tim.init(freq=2.5, mode=Timer.PERIODIC, callback=tick)

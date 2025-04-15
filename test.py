import paho.mqtt.client as mqtt

# Callback when the client connects to the broker
def on_connect(client, userdata, flags, rc):
    print("Connected with result code " + str(rc))
    # Subscribe to the desired topics
    client.subscribe("aquaponics/change_water")
    client.subscribe("aquaponics/turbidity")

# Callback when a message is received from the broker
def on_message(client, userdata, msg):
    print(f"Received message on topic '{msg.topic}': {msg.payload.decode()}")

# Create an MQTT client instance
client = mqtt.Client()

# Assign the callback functions
client.on_connect = on_connect
client.on_message = on_message

# Connect to the MQTT broker
client.connect("7170b6ffae904900aeec54b1aeffca2c.s1.eu.hivemq.cloud", 8883, 60)

# Start the network loop, this call is blocking and runs forever
client.loop_forever()

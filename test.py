import paho.mqtt.client as paho
from paho import mqtt

# setting callbacks for different events to see if it works, print the message etc.
# setting callbacks for different events to see if it works, print the message etc.
def on_connect(_client, _userdata, _flags, rc, _properties=None):
    print("CONNACK received with code %s." % rc)
# with this callback you can see if your publish was successful
# with this callback you can see if your publish was successful
def on_publish(_client, _userdata, mid, reasonCode, _properties=None):
    print("mid: " + str(mid))
# print which topic was subscribed to
# print which topic was subscribed to
def on_subscribe(_client, _userdata, mid, granted_qos, _properties=None):
    print("Subscribed: " + str(mid) + " " + str(granted_qos))
# print message, useful for checking if it was successful
# print message, useful for checking if it was successful
def on_message(_client, _userdata, msg):
    print(msg.topic + " " + str(msg.qos) + " " + str(msg.payload))
# using MQTT version 5 here, for 3.1.1: MQTTv311, 3.1: MQTTv31
# userdata is user defined data of any type, updated by user_data_set()
# client_id is the given name of the client
client = paho.Client(client_id="", userdata=None, protocol=paho.MQTTv5, callback_api_version=paho.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect

# enable TLS for secure connection
client.tls_set(tls_version=mqtt.client.ssl.PROTOCOL_TLS)
# set username and password
client.username_pw_set("hivemq.webclient.1744714440909", "dG3:7lS,WogeVpO;P1?0")
# connect to HiveMQ Cloud on port 8883 (default for MQTT)
client.connect("7170b6ffae904900aeec54b1aeffca2c.s1.eu.hivemq.cloud", 8883)

# setting callbacks, use separate functions like above for better visibility
client.on_subscribe = on_subscribe
client.on_message = on_message
client.on_publish = on_publish

# subscribe to all topics of encyclopedia by using the wildcard "#"
client.subscribe("encyclopedia/#", qos=1)

# a single publish, this can also be done in loops, etc.
client.publish("encyclopedia/temperature", payload="hot", qos=1)

# loop_forever for simplicity, here you need to stop the loop manually
# you can also use loop_start and loop_stop
client.loop_forever()
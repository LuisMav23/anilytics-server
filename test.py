import paho.mqtt.client as paho
from paho import mqtt

def on_connect(_client, _userdata, _flags, rc, _properties=None):
    print("CONNACK received with code %s." % rc)

def on_publish(_client, _userdata, mid, reasonCode, _properties=None):
    print("mid: " + str(mid))

def on_subscribe(_client, _userdata, mid, granted_qos, _properties=None):
    print("Subscribed: " + str(mid) + " " + str(granted_qos))

def on_message(_client, _userdata, msg):
    print(msg.topic + " " + str(msg.qos) + " " + str(msg.payload))

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
client.subscribe("aquaponics/#")

# loop_forever for simplicity, here you need to stop the loop manually
# you can also use loop_start and loop_stop
client.loop_forever()
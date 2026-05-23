# ecoflow-powerstream-scripts
The python scripts I'm using to integrate the Ecoflow Powerstream locally with Home Assistant and Node-Red.

# How the PowerStream is connected
The PowerStream is connected to WiFi, but in its own VLAN with no internet access. Through DNS rewrites (on my Unifi Gateway) all traffic to mqtt-e.ecoflow.com and mqtt.ecoflow.com (not sure if this one is even needed) is redirected to my Home Assistant IP. I'm running the EMQX MQTT Broker on Home Assistant, it is available in the official Add-on / App Store. It comes with a self-signed certificate preinstalled for testing, which makes it really easy to connect the PowerStream. I connected it by first having it connect to the Ecoflow Cloud, and then disabling internet access and enabling the DNS rewrite, that way it just worked. When configuring WiFi for the first time, it receives the MQTT credentials first, which is why I just connected it to the cloud before switching over to my local solution, but there are repos which have solutions for the first-time WiFi config as well, atleast I think so.

# Receiving / decoding data
As soon as the PowerStream is connected to the MQTT server, it will send data every 40-50 seconds. Because I didn't need it to update more often, I just left it as is. There is a command to trigger updates, but I didn't need it and it worked fine like this for ~1 year now. The script in "receive" connects to the MQTT broker, receives these messages, decodes them and sends them to another MQTT topic. This topic is then used in Node-Red for automations and to set the sensor values in Home Assistant.

# Sending / encoding data
There are only 2 commands that I need for what I am doing: The battery / grid priority switch and the baseload feed-in value to the grid.
Because the PowerStream does not care at all about the timestamps in the commands, I just hardcoded them for a while and "pre-generated" them with the protoc-CLI-tool and the Protobuf definitions and pasted the results into Node-Red and sent them to the Powerstream over MQTT. That worked perfectly fine, but at some point I wanted to set the feed-in value to any integer, and not just pre-defined ones.
In the "send" folder is a simple FastAPI server, which can generate the payloads required to set the feed-in value to any numeric value. It provides an endpoint, Node-Red sends the value the feed-in value should be set to, the scripts generates the payload with the Protobuf definition and the required cmd_ids and returns the payload to Node-Red, which then sends it to the PowerStream over MQTT. It should be pretty easy to expand the script to support more commands, you just need the command ids. The "seq" value for the time is hardcoded. It should be a Unix timestamp, and the correct way to do it is also written as a comment in the code, but in my testing I used this hardcoded value for so long, and it always worked, that I decided to keep it because "never change a running system". It's probably a good idea to change this, though.

## Attribution

This project is based on my own experiments with local EcoFlow PowerStream MQTT
communication.

Parts of the protocol knowledge used here, especially the EcoFlow PowerStream
protobuf schemas, field mappings, and command identifiers, are based on research
and implementation work from the ioBroker EcoFlow MQTT adapter:

- `foxthefox/ioBroker.ecoflow-mqtt`

That project is licensed under the MIT License. The original copyright and
license notice of that project should be preserved when reusing substantial
parts derived from it.


## License

This repository is provided as a personal hobby project for educational,
experimental, and non-commercial use.

You may use, copy, modify, and adapt the code as a basis for your own personal
or non-commercial projects. Commercial use is not permitted without prior
written permission.

## Disclaimer

Use this project at your own risk.

The scripts can send commands to an EcoFlow PowerStream device. Wrong commands,
wrong values, software bugs, configuration mistakes, or changes in EcoFlow's
firmware/protocol may cause unexpected behavior.

The author is not responsible for any damage, data loss, malfunction, device
failure, warranty issues, safety issues, incorrect power settings, grid export,
electrical problems, or any other consequences arising from the
use or misuse of this software.

You are responsible for understanding what the scripts do before running them
and for complying with all applicable laws, regulations, electrical safety
requirements, grid operator rules, and device warranty terms.

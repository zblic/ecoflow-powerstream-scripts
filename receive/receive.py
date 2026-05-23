import json
import logging
import os
import signal
import sys
import time
from typing import Any

import paho.mqtt.client as mqtt
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import DecodeError

import powerstream_pb2 as pb


MQTT_HOST = os.getenv("MQTT_HOST", "YOUR_MQTT_SERVER")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")

IN_TOPIC = os.getenv("POWERSTREAM_IN_TOPIC", "/sys/75/SERIAL_NUMBER/thing/protobuf/upstream")

OUT_ROOT = os.getenv("POWERSTREAM_OUT_ROOT", "ecoflow/powerstream_decoded")

CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "powerstream-protobuf-decoder")

RETAIN_STATE = os.getenv("RETAIN_STATE", "false").lower() in ("1", "true", "yes")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LAST_STATE = {}

MESSAGE_TYPES = {
    # PowerStream Heartbeat
    (20, 1): ("inverter_heartbeat", pb.inverter_heartbeat),

    # Zweiter Heartbeat / Zusatzdaten
    (20, 4): ("InverterHeartbeat2", pb.InverterHeartbeat2),

    # History / PowerPack, erstmal dekodieren und mit ausgeben, eigentlich unwichtig
    (254, 32): ("PowerPack", pb.PowerPack),
    (20, 136): ("PowerPack", pb.PowerPack),
    (20, 138): ("PowerPack", pb.PowerPack),
}


def number(value: Any) -> float | int | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def tenth(value: Any) -> float | None:
    value = number(value)
    if value is None:
        return None
    return round(value / 10, 3)


def millis(value: Any) -> float | None:
    value = number(value)
    if value is None:
        return None
    return round(value / 1000, 3)


def add_if_present(target: dict[str, Any], out_name: str, source: dict[str, Any], field: str, scale=None) -> None:
    if field not in source:
        return

    value = source.get(field)
    if scale:
        value = scale(value)

    if value is not None:
        target[out_name] = value


def decode_inner_message(header: Any) -> dict[str, Any]:
    cmd_func = int(header.cmd_func)
    cmd_id = int(header.cmd_id)
    message_info = MESSAGE_TYPES.get((cmd_func, cmd_id))

    base = {
        "cmd_func": cmd_func,
        "cmd_id": cmd_id,
        "device_sn": header.device_sn,
        "payload_ver": int(header.payload_ver),
        "version": int(header.version),
    }

    if not message_info:
        base["type"] = "unknown"
        base["pdata_len"] = len(header.pdata)
        return base

    type_name, message_class = message_info

    inner = message_class()
    inner.ParseFromString(header.pdata)

    data = MessageToDict(
        inner,
        preserving_proto_field_name=True,
    )

    base["type"] = type_name
    base["data"] = data
    return base


def build_state(decoded_items: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    state: dict[str, Any] = {}
    device_sn = "unknown"

    for item in decoded_items:
        if item.get("device_sn"):
            device_sn = item["device_sn"]

        msg_type = item.get("type")
        data = item.get("data") or {}

        if msg_type == "inverter_heartbeat":
            add_if_present(state, "pv1_input_watts", data, "pv1InputWatts", tenth)
            add_if_present(state, "pv2_input_watts", data, "pv2InputWatts", tenth)

            pv1 = tenth(data.get("pv1InputWatts"))
            pv2 = tenth(data.get("pv2InputWatts"))
            if pv1 is not None or pv2 is not None:
                state["pv_input_watts_total"] = round((pv1 or 0) + (pv2 or 0), 3)

            add_if_present(state, "pv1_input_volt", data, "pv1InputVolt", tenth)
            add_if_present(state, "pv2_input_volt", data, "pv2InputVolt", tenth)

            add_if_present(state, "battery_input_watts", data, "batInputWatts", tenth)
            add_if_present(state, "battery_input_volt", data, "batInputVolt", tenth)
            add_if_present(state, "battery_soc", data, "batSoc")

            add_if_present(state, "inverter_output_watts", data, "invOutputWatts", tenth)
            add_if_present(state, "inverter_ac_volt", data, "invOpVolt", tenth)
            add_if_present(state, "inverter_frequency_hz", data, "invFreq", tenth)

            add_if_present(state, "permanent_watts", data, "permanentWatts", tenth)

            add_if_present(state, "supply_priority", data, "supplyPriority")
            add_if_present(state, "feed_priority", data, "feedPriority")
            add_if_present(state, "lower_limit", data, "lowerLimit")
            add_if_present(state, "upper_limit", data, "upperLimit")

            add_if_present(state, "wifi_rssi", data, "wifi_rssi")
            add_if_present(state, "pv_to_inv_watts", data, "pv_to_inv_watts", tenth)
            add_if_present(state, "ac_set_watts", data, "ac_set_watts", tenth)


            add_if_present(state, "llc_temp", data, "llcTemp", tenth)
            add_if_present(state, "pv1_input_cur", data, "pv1InputCur", tenth)
            add_if_present(state, "pv2_input_cur", data, "pv2InputCur", tenth)

        elif msg_type == "InverterHeartbeat2":
            add_if_present(state, "wifi_rssi_2", data, "wifiRssi")
            add_if_present(state, "uptime", data, "uptime")

    if device_sn == "unknown":
        device_sn = state.get("device_sn", "unknown")

    previous_state = LAST_STATE.get(device_sn, {})
    previous_state.update(state)

    previous_state["device_sn"] = device_sn
    previous_state["updated_at"] = int(time.time())

    LAST_STATE[device_sn] = previous_state

    return device_sn, previous_state


def decode_powerstream_payload(payload: bytes) -> list[dict[str, Any]]:
    outer = pb.Message()
    outer.ParseFromString(payload)

    decoded_items: list[dict[str, Any]] = []

    for header in outer.header:
        if not header.pdata:
            continue

        decoded_items.append(decode_inner_message(header))

    return decoded_items


def publish_json(client: mqtt.Client, topic: str, payload: Any, retain: bool = False) -> None:
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    result = client.publish(topic, text, qos=0, retain=retain)

    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        logging.warning("Publish failed topic=%s rc=%s", topic, result.rc)


def on_connect(client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any = None) -> None:
    logging.info("Connected to MQTT broker with reason_code=%s", reason_code)
    client.subscribe(IN_TOPIC, qos=0)
    logging.info("Subscribed to %s", IN_TOPIC)


def on_message(client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
    try:
        decoded_items = decode_powerstream_payload(msg.payload)
        if not decoded_items:
            logging.debug("No decodable headers in topic=%s", msg.topic)
            return

        device_sn, state = build_state(decoded_items)

        publish_json(
            client,
            f"{OUT_ROOT}/{device_sn}/state",
            state,
            retain=RETAIN_STATE,
        )

        publish_json(
            client,
            f"{OUT_ROOT}/{device_sn}/raw",
            {
                "source_topic": msg.topic,
                "items": decoded_items,
                "updated_at": int(time.time()),
            },
            retain=False,
        )

        unknown_items = [item for item in decoded_items if item.get("type") == "unknown"]
        if unknown_items:
            publish_json(
                client,
                f"{OUT_ROOT}/{device_sn}/unknown",
                {
                    "source_topic": msg.topic,
                    "items": unknown_items,
                    "updated_at": int(time.time()),
                },
                retain=False,
            )

    except DecodeError as exc:
        logging.warning("Protobuf decode error topic=%s error=%s", msg.topic, exc)
    except Exception:
        logging.exception("Unexpected error while decoding topic=%s", msg.topic)


def make_client() -> mqtt.Client:
    client = mqtt.Client(
        client_id=CLIENT_ID,
        protocol=mqtt.MQTTv311
    )

    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    client.on_connect = on_connect
    client.on_message = on_message

    return client


def main() -> int:
    logging.basicConfig(
        level=LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    client = make_client()

    stop = False

    def handle_stop(signum, frame):
        nonlocal stop
        stop = True
        logging.info("Stopping...")

    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)

    logging.info("Connecting to MQTT broker %s:%s", MQTT_HOST, MQTT_PORT)
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()

    try:
        while not stop:
            time.sleep(1)
    finally:
        client.loop_stop()
        client.disconnect()

    return 0


if __name__ == "__main__":
    sys.exit(main())

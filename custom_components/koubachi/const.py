DOMAIN = "koubachi"

CONF_MAC = "mac"
CONF_KEY = "key"
CONF_CALIBRATION = "calibration"

CONTENT_TYPE = "application/x-koubachi-aes-encrypted"


def signal_new_reading(mac: str, sensor_type: str) -> str:
    return f"koubachi_new_reading_{mac}_{sensor_type}"

import json
import paho.mqtt.client as mqtt

class MQTTManager:
    """Manages all MQTT connection and communication logic."""
    
    def __init__(self, device_id, config, logger, app):
        self.device_id = device_id
        self.config = config
        self.logger = logger
        self.app = app # Reference to the main app to call its methods
        self.client = None
        
        if self.config.get('enabled', False):
            self.connect()

    def connect(self):
        """Establishes connection to the MQTT broker."""
        try:
            self.logger.info("Connecting to MQTT broker...")
            self.client = mqtt.Client()
            self.client.on_connect = self._on_connect
            self.client.on_message = self._on_message
            
            self.client.username_pw_set(self.config["username"], self.config["password"])
            self.client.connect(self.config["host"], int(self.config["port"]))
            self.client.loop_start()
        except Exception as e:
            self.logger.error(f"Failed to connect to MQTT: {e}", exc_info=True)

    def _on_connect(self, client, userdata, flags, rc):
        """Callback for when the client connects to the broker."""
        if rc == 0:
            self.logger.info("Successfully connected to MQTT broker.")
            topic = f"tm_webcams/{self.device_id}/command"
            self.logger.info(f"Subscribing to command topic: {topic}")
            self.client.subscribe(topic)
        else:
            self.logger.error(f"Failed to connect to MQTT, return code: {rc}")

    def _on_message(self, client, userdata, message):
        """Callback for when a message is received."""
        try:
            topic = message.topic
            payload = json.loads(message.payload)
            self.logger.info(f"Received MQTT command on topic '{topic}': {payload}")
            
            if topic == f"tm_webcams/{self.device_id}/command":
                action = payload.get("action")
                if action == "capture":
                    self.app.trigger_capture()
                elif action == "restart":
                    self.logger.warning("Restart command received via MQTT. Shutting down.")
                    self.app.publish_diagnostic("Restarting")
                    self.app.shutdown()
                elif action == "diagnostic":
                    self.app.publish_diagnostic()
                else:
                    self.logger.warning(f"Unknown MQTT action received: {action}")
        except json.JSONDecodeError:
            self.logger.error("Failed to decode MQTT message payload.")
        except Exception as e:
            self.logger.error(f"Error processing MQTT message: {e}", exc_info=True)

    def publish(self, topic, payload):
        """Publishes a message to a given MQTT topic."""
        if not self.client or not self.client.is_connected():
            return

        try:
            full_topic = f"tm_webcams/{self.device_id}/{topic}"
            result, mid = self.client.publish(full_topic, json.dumps(payload))
            if result != mqtt.MQTT_ERR_SUCCESS:
                self.logger.error(f"Failed to publish to {full_topic}, result code: {result}")
        except Exception as e:
            self.logger.error(f"Exception while publishing MQTT message: {e}", exc_info=True)
            
    def disconnect(self):
        """Stops the MQTT client loop."""
        if self.client:
            self.client.loop_stop()
            self.logger.info("MQTT client disconnected.")
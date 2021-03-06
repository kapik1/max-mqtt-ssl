import logging
import multiprocessing
import time
import ssl

import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish


class MQTTClient(multiprocessing.Process):
    def __init__(self, messageQ, commandQ, config):
        self.logger = logging.getLogger('Max!-MQTT.MQTTClient')
        self.logger.info("Starting...")

        multiprocessing.Process.__init__(self)
        self.messageQ = messageQ
        self.commandQ = commandQ

        self.mqttDataPrefix = config['mqtt_prefix']
        self.mqtt_host = config['mqtt_host']
        self.mqtt_port = config['mqtt_port']

        self._mqttConn = mqtt.Client(client_id='Max-MQTT'
                                               '', clean_session=True, userdata=None)# auth=self.auth)

        self._mqttConn.tls_set(ca_certs='/root/max/max-mqtt/industrial.pem', certfile=None,
                keyfile=None, cert_reqs=ssl.CERT_REQUIRED,
                tls_version=ssl.PROTOCOL_TLSv1_2, ciphers=None)

        self._mqttConn.tls_insecure_set(False)
        self._mqttConn.username_pw_set(config['username'], password=config['password'])
        self._mqttConn.connect(self.mqtt_host, port=self.mqtt_port, keepalive=120)
        self._mqttConn.on_disconnect = self._on_disconnect
        self._mqttConn.on_publish = self._on_publish
        self._mqttConn.on_message = self._on_message

        self.message_timeout = config['mqtt_message_timeout']

    def close(self):
        self.logger.info("Closing connection")
        self._mqttConn.disconnect()

    def _on_disconnect(self, client, userdata, rc):
        if rc != 0:
            self.logger.error("Unexpected disconnection.")
            time.sleep(1)
            self._mqttConn.reconnect()

    def _on_publish(self, client, userdata, mid):
        self.logger.debug("Message " + str(mid) + " published.")

    def _on_message(self, client, userdata, message):
        self.logger.debug("Message received: %s" % (message))

        data = message.topic.replace(self.mqttDataPrefix + "/", "").split("/")
        data_out = {
            'method': 'command',
            'topic': message.topic,
            'deviceId': data[0],
            'param': data[1],
            'payload': message.payload.decode('ascii'),
            'qos': 1,
            'timestamp': time.time()
        }
        self.commandQ.put(data_out)
        if message.retain != 0:
            (rc, final_mid) = self._mqttConn.publish(message.topic, None, 1, True)
            self.logger.info("Clearing topic " + message.topic)

    def publish(self, task):
        if task['timestamp'] <= time.time() + self.message_timeout:
            topic = "%s/%s/%s" % (self.mqttDataPrefix, task['deviceId'], task['param'])
            try:
                if task['payload'] is not None:
                    publish.single(topic, hostname=self.mqtt_host, port=self.mqtt_port, auth={'username':config['username'],'password':config['password']},tls={}, payload=task['payload'])
                    
                    self.logger.debug('Sending:%s' % (task))
            except Exception as e:
                self.logger.error('Publish problem: %s' % (e))
                self.messageQ.put(task)

    def run(self):
        self._mqttConn.subscribe(self.mqttDataPrefix + "/+/+/set")
        while True:
            while not self.messageQ.empty():
                task = self.messageQ.get()
                if task['method'] == 'publish':
                    self.publish(task)
            time.sleep(0.01)
            self._mqttConn.loop()

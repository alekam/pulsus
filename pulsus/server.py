from gevent import monkey; monkey.patch_all()
from gevent.http import HTTPServer
from gevent.httplib import HTTPResponse
import sys
import os
import json
import gevent
import logging
import logging.config
import ConfigParser


from pulsus.services.apns import NotificationService, NotificationMessage
from pulsus.services.bbp import BlackBerryPushService, BlackBerryPushNotification

class APIServer(HTTPServer):
    def __init__(self, *args, **kwargs):
        self.apns = kwargs.pop('apns')
        self.bbp = kwargs.pop('bbp')
        super(APIServer, self).__init__(*args, **kwargs)
        self.log = logging.getLogger('pulsus.server')

    def handle(self, request):
        headers = request.get_input_headers()
        if request.uri == '/api/push/' and request.typestr == 'POST':
            json_data = request.input_buffer.read(-1)
            notifications = json.loads(json_data)
            self.push_notifications(notifications)
            request.send_reply(201, "CREATED", 'hello')
        request.send_reply_end()

    def push_notifications(self, notifications):
        for notification in notifications:
            if notification['type'] == 'apns':
                self.push_apns(notification)
            elif notification['type'] == 'c2dm':
                self.push_c2dm(notification)
            elif notification['type'] == 'bbp':
                self.push_bbp(notification)
            else:
                self.log.error("Unknown push type")

    def push_c2dm(self, notification):
        pass

    def push_bbp(self, notification):
        self.log.debug("Sending BBP notification")
        n = BlackBerryPushNotification(notification['device_pins'],
                                       notification['message'])
        self.bbp.push(n)

    def push_apns(self, notification):
        self.log.debug("Sending APNS notification")
        token = notification['token'].decode('hex')
        kwargs = dict()
        for attr in ['alert', 'badge', 'extra', 'sound']:
            if attr in notification:
                kwargs[attr] = notification[attr]
        message = NotificationMessage(token,
                                      **kwargs)
        self.apns.send(message)



def apns_feedback_handler(apns):
    for fb in apns.get_feedback():
        print fb



def main():
    assert len(sys.argv) == 2, "Usage: pulsus <config_dir>"
    
    config_dir = sys.argv[1]
    
    config = ConfigParser.ConfigParser()
    config.read([os.path.join(config_dir, 'pulsus.conf')])
    logging.config.fileConfig(os.path.join(config_dir, 'logging.conf'))

    # Apple
    apns_server = NotificationService(certfile=config.get('apns', 'cert_file_pem'))
    apns_server.start()
    
    gevent.spawn(apns_feedback_handler, apns_server)

    # BlackBerry
    bbp_server = BlackBerryPushService(config.get('blackberry', 'app_id'),
                                       config.get('blackberry', 'password'),
                                       config.get('blackberry', 'push_url'))
    bbp_server.start()

    # API
    api_server = APIServer((config.get('server','address'),
                            config.getint('server','port')), 
                           apns=apns_server,
                           bbp=bbp_server)
    logging.info("Pulsus started")
    api_server.serve_forever()

    

if __name__ == "__main__":
    main()
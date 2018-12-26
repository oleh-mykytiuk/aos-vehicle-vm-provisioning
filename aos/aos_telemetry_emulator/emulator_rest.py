import json
import logging
import os
import signal
import sys
import time
from threading import Thread
from http.server import HTTPServer

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telemetry_emulator.config import (
    EMULATOR_UPDATE_TIME, CONTROL_API_ADDRESS, DRIVER_UUID, VEHICLE_VIN
)
from telemetry_emulator.control_api import EmulatorCommandsRequestHandler, BadRequestException
from telemetry_emulator.emulator import VertexPool, Emulator

logger = logging.getLogger(__name__)


class RestEmulatorCommandsRequestHandler(EmulatorCommandsRequestHandler):
    def setup(self):
        super().setup()
        self._urls.extend([
            (r'^/stats/?$', self._stats),
            (r'^/attributes/?$', self._set_attributes)
        ])

    def response(self, status, body=None, headers: dict = None):
        self.send_response(status)
        if headers:
            for k, v in headers.items():
                self.send_header(keyword=k, value=v)
        self.end_headers()
        if body is not None:
            self.wfile.write(body)

    def _stats(self):
        data = json.dumps({
            "driver": DRIVER_UUID,
            "vin": VEHICLE_VIN,
            "telemetry": self.emulator.get_data()
        }).encode("utf-8")
        self.response(200, body=data, headers={"Content-Type": "application/json"})

    def do_POST(self):
        return self.do_GET()

    def _set_attributes(self):
        data_len = int(self.headers.get('Content-Length', 0))
        try:
            data = json.loads(self.rfile.read(data_len).decode("utf-8"))
            self.update_emulator(**data)
            self.response(201)
        except json.JSONDecodeError:
            raise BadRequestException

    def update_emulator(self, rectangle_long0=None, rectangle_lat0=None, rectangle_long1=None, rectangle_lat1=None,
                        to_rectangle=None, stop=None, tire_break=None, *args, **kwargs):
        # Rectangle
        if all((rectangle_long0, rectangle_lat0, rectangle_long1, rectangle_lat1,)):
            self.emulator.set_rectangle(
                long0=rectangle_long0,
                lat0=rectangle_lat0,
                long1=rectangle_long1,
                lat1=rectangle_lat1
            )
        else:
            self.emulator.del_rectangle()

        # Rectangle direction
        if to_rectangle is not None:
            self.emulator.set_rectangle_direction(target=to_rectangle)

        # Stop
        if stop is not None:
            if stop:
                self.emulator.command_stop()
            else:
                self.emulator.command_go()

        # Tire break
        if tire_break:
            self.emulator.tire_break()


class RestEmulatorAPIServer(HTTPServer):
    def __init__(self, server_address, emulator):
        super().__init__(server_address, RestEmulatorCommandsRequestHandler)
        self.emulator = emulator


def signal_handler(signum, frame):
    if signum == 15:
        control_server.shutdown()
        print('got SIGTERM')
        sys.exit(0)


def emulator_loop(emulator):
    delta = time.time()
    while True:
        time.sleep(EMULATOR_UPDATE_TIME)
        emulator.update(time.time() - delta)
        delta = time.time()


if __name__ == '__main__':
    # logging setup
    logger.addHandler(logging.StreamHandler())
    logger.setLevel(logging.DEBUG)
    tl = logging.getLogger('control_api')
    tl.addHandler(logging.StreamHandler())
    tl.setLevel(logging.DEBUG)

    base_dir = os.path.dirname(__file__)
    vp = VertexPool(os.path.join(base_dir, 'map.json'))
    emulator = Emulator(vp)
    control_server = RestEmulatorAPIServer(CONTROL_API_ADDRESS, emulator)

    signal.signal(signal.SIGTERM, signal_handler)

    server_thread = Thread(target=control_server.serve_forever, daemon=False)
    server_thread.start()
    try:
        emulator_loop(emulator)
    except KeyboardInterrupt:
        logger.info("received Keyboard interrupt. shutting down")
        control_server.shutdown()
        server_thread.join()

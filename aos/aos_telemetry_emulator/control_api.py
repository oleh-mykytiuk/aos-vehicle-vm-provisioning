import logging
import re
from http.server import BaseHTTPRequestHandler, HTTPServer

logger = logging.getLogger(__name__)


class HttpResponseException(Exception):
    def __init__(self, code, message=None):
        self.code = code
        self.message = message


class BadRequestException(HttpResponseException):
    def __init__(self, message=None):
        super().__init__(400, message)


class NotFoundException(HttpResponseException):
    def __init__(self, message=None):
        super().__init__(404, message)


class ControlApiSever(HTTPServer):
    def __init__(self, server_address, emulator):
        super().__init__(server_address, EmulatorCommandsRequestHandler)
        self.emulator = emulator


class EmulatorCommandsRequestHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self._urls = [
            (r'^/start/?$', self._start),
            (r'^/stop/?$', self._stop),
            (r'^/tire_break/?$', self.tire_break),
            (r'^/madness/(?P<value>\d+(\.\d+)?)/?$', self._madness),
            (r'^/del-rectangle/?$', self._del_rectangle),
            (r'^/rectangle-in/?$', self._rectangle_in),
            (r'^/rectangle-out/?$', self._rectangle_out),
            (r'^/test-rectangle/?$', self._test_rectangle),
            (
                r'^/rectangle/(?P<x0>\d+(\.\d+)?)/(?P<y0>\d+(\.\d+)?)/(?P<x1>\d+(\.\d+)?)/(?P<y1>\d+(\.\d+)?)/?$',
                self._set_rectangle
            ),
        ]

    @property
    def emulator(self):
        return self.server.emulator

    def do_GET(self):
        request_path = self.path
        try:
            self._handle(request_path)
        except HttpResponseException as ex:
            self.response(ex.code, ex.message.encode('utf8') if ex.message is not None else None)
        except Exception as ex:
            logger.exception("Unexpected exception in handling request", exc_info=ex)
            self.response(500, str(ex).encode('utf8'))

    def _handle(self, request_path):
        for url_pattern, handle_function in self._urls:
            m = re.match(url_pattern, request_path)
            if m:
                handle_function(**m.groupdict())
                return
        raise NotFoundException()

    def response(self, status, body=None):
        self.send_response(status)
        self.end_headers()
        if body is not None:
            self.wfile.write(body)

    def _start(self):
        logger.debug("start")
        success = self.emulator.command_go()
        logger.debug("success: {success}".format(success=success))
        self.response(200)

    def _stop(self):
        logger.debug("stop")
        success = self.emulator.command_stop()
        logger.debug("success: {success}".format(success=success))
        self.response(200)

    def tire_break(self):
        logger.debug("tire_break")
        success = self.emulator.tire_break()
        logger.debug("success: {success}".format(success=success))
        self.response(200)

    def _madness(self, value):
        logger.debug("madness set to {}".format(value))
        madness = float(value)
        if madness == 0:
            self.emulator.change_madness_periodically = True
        elif 0 < madness <= 1:
            self.emulator.change_madness_periodically = False
            self.emulator.madness = madness
        else:
            raise BadRequestException(message='Madness must be between 0 and 1')
        self.response(200)

    def _set_rectangle(self, x0, y0, x1, y1):
        logger.debug("Rectangle is set to {x0}:{y0} {x1}:{y1}".format(x0=x0, y0=y0, x1=x1, y1=y1))
        self.emulator.set_rectangle(x0, y0, x1, y1)
        self.response(200)

    def _del_rectangle(self):
        self.emulator.del_rectangle()
        self.response(200)

    def _test_rectangle(self):
        """
        Sets test rectangle around the car
        """
        x = self.emulator.x
        y = self.emulator.y
        dxy = 1000
        logger.debug("Rectangle is set")
        self.emulator.set_rectangle(
            self.emulator.vertex_pool.x_to_lon(x - dxy),
            self.emulator.vertex_pool.y_to_lat(y - dxy),
            self.emulator.vertex_pool.x_to_lon(x + dxy),
            self.emulator.vertex_pool.y_to_lat(y + dxy)
        )
        self.response(200)

    def _rectangle_in(self):
        self.emulator.set_rectangle_direction(True)
        self.response(200)

    def _rectangle_out(self):
        self.emulator.set_rectangle_direction(False)
        self.response(200)

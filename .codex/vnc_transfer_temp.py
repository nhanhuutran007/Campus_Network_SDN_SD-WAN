import base64
import gzip
from pathlib import Path

from vncdotool import api


source = Path("configs/01-Site100-Campus/campus_switch_13.py")
payload = base64.b64encode(gzip.compress(source.read_bytes())).decode("ascii")


def shifted(client, key):
    client.keyDown("shift")
    client.keyPress(key)
    client.keyUp("shift")


def type_text(client, value):
    for character in value:
        client.keyPress("minus" if character == "-" else character)


with api.connect("10.215.28.26::33545", password=None) as client:
    client.timeout = 300
    client.keyPress("ctrl-c")
    type_text(client, "echo " + payload + " ")
    shifted(client, "\\")  # pipe
    type_text(client, " base64 -d ")
    shifted(client, "\\")  # pipe
    type_text(client, " gzip -d ")
    shifted(client, ".")  # greater-than
    type_text(client, " /tmp/app.py")
    client.keyPress("enter")
    client.pause(3)
    type_text(client, "sha256sum /tmp/app.py")
    client.keyPress("enter")

import getpass

from vncdotool import api


password = getpass.getpass("Node 9 root password: ")
with api.connect("10.215.28.26::33545", password=None) as client:
    client.timeout = 10
    for character in password:
        client.keyPress(character)
    client.keyPress("enter")

print("Da gui mat khau vao console node 9.")
input("Nhan Enter de dong cua so: ")

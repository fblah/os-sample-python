from flask import Flask
application = Flask(__name__)

from requests import get

ip = get('https://api.ipify.org').text
print 'My public IP address is:', ip

import threading
from multiprocessing import Queue
q = Queue()

import socket
import struct
import sys
from collections import namedtuple

FullCone = "Full Cone"  # 0
RestrictNAT = "Restrict NAT"  # 1
RestrictPortNAT = "Restrict Port NAT"  # 2
SymmetricNAT = "Symmetric NAT"  # 3
UnknownNAT = "Unknown NAT" # 4
NATTYPE = (FullCone, RestrictNAT, RestrictPortNAT, SymmetricNAT, UnknownNAT)

def addr2bytes(addr, nat_type_id):
    """Convert an address pair to a hash."""
    host, port = addr
    try:
        host = socket.gethostbyname(host)
    except (socket.gaierror, socket.error):
        raise ValueError("invalid host")
    try:
        port = int(port)
    except ValueError:
        raise ValueError("invalid port")
    try:
        nat_type_id = int(nat_type_id)
    except ValueError:
        raise ValueError("invalid NAT type")
    bytes = socket.inet_aton(host)
    bytes += struct.pack("H", port)
    bytes += struct.pack("H", nat_type_id)
    return bytes



def worker(port = 5678):
       
    q.put("trying to open udp socket")
    sockfd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sockfd.bind(("", port))
    
    q.put("listening on *:%d (udp)" % port)

    poolqueue = {}
    # A,B with addr_A,addr_B,pool=100
    # temp state {100:(nat_type_id, addr_A, addr_B)}
    # final state {addr_A:addr_B, addr_B:addr_A}
    symmetric_chat_clients = {}
    ClientInfo = namedtuple("ClientInfo", "addr, nat_type_id")
    while True:
        data, addr = sockfd.recvfrom(1024)
        datas = str(data).replace("'","").replace("b","")
        data = datas
        if data.startswith("msg "):
            # forward symmetric chat msg, act as TURN server
            try:
                sockfd.sendto(data[4:], symmetric_chat_clients[addr])
                q.put("msg successfully forwarded to {0}".format(symmetric_chat_clients[addr]))
                q.put(data[4:])
            except KeyError:
                q.put("something is wrong with symmetric_chat_clients!")
        else:
            # help build connection between clients, act as STUN server
            q.put("connection from %s:%d" % addr)
            pool, nat_type_id = data.strip().split()
            sockfd.sendto("ok {0}".format(pool), addr)
            q.put("pool={0}, nat_type={1}, ok sent to client".format(pool, NATTYPE[int(nat_type_id)]))
            data, addr = sockfd.recvfrom(2)
            if data != "ok":
                continue

            q.put("request received for pool:", pool)

            try:
                a, b = poolqueue[pool].addr, addr
                nat_type_id_a, nat_type_id_b = poolqueue[pool].nat_type_id, nat_type_id
                sockfd.sendto(addr2bytes(a, nat_type_id_a), b)
                sockfd.sendto(addr2bytes(b, nat_type_id_b), a)
                q.put("linked", pool)
                del poolqueue[pool]
            except KeyError:
                poolqueue[pool] = ClientInfo(addr, nat_type_id)

            if pool in symmetric_chat_clients:
                if nat_type_id == '3' or symmetric_chat_clients[pool][0] == '3':
                    # at least one is symmetric NAT
                    recorded_client_addr = symmetric_chat_clients[pool][1]
                    symmetric_chat_clients[addr] = recorded_client_addr
                    symmetric_chat_clients[recorded_client_addr] = addr
                    q.put("Hurray! symmetric chat link established.")
                    del symmetric_chat_clients[pool]
                else:
                    del symmetric_chat_clients[pool]  # neither clients are symmetric NAT
            else:
                symmetric_chat_clients[pool] = (nat_type_id, addr)



log = ""
@application.route("/")
def hello():
    global log
    if(not q.empty()):
        item = q.get()
        log += item
    return "Hello World! I am " + ip + "\n" + log

def worker2():
    print "Start Flask" 
    if(sys.argv[1]):
        application.run(port= int(sys.argv[2]))
    else:
        application.run(port=8080)
    
if __name__ == "__main__":
    print sys.argv
    t = threading.Thread(target=worker2)
    #t.daemon = True
    t.start()
    if(sys.argv[1]):
        worker(int(sys.argv[1]))
    else:
        worker()
    
    q.join()

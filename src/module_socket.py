import socket
import json
import threading
from naoqi import ALProxy

class SocketClient(threading.Thread):
    def __init__(self, server_addr, server_port):
        super(SocketClient, self).__init__()
        self.server_addr = server_addr
        self.server_port = server_port
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connected = False
        self.running = True

        self.speech = ALProxy('ALAnimatedSpeech')
        self.memory = ALProxy("ALMemory")

    def connection(self):
        try:
            self.client_socket.connect((self.server_addr, self.server_port))
            self.connected = True

        except socket.error as e:
            print("Socket error:", e)
            self.client_socket.close()
            self.connected = False

    def run(self):
        while not self.connected and self.running:
            self.connection()
        while self.running:
            response = self.client_socket.recv(4096)
            try:
                json_data = json.loads(response.decode('utf-8'))
                if(json_data['type'] == 'script'):
                    msg = str(json_data['message'])
                    if msg:
                        self.memory.raiseEvent('StopAction', None)
                        self.memory.raiseEvent('Say', msg)

                elif(json_data['type'] == 'profile'):
                    if('html' in json_data['message']):
                        self.memory.raiseEvent("LoadHTML", "http://198.18.0.1/apps/rmit-race/"+str(json_data['message']['html']))
                    if('flags' in json_data['message']):
                        if('gap_fill' in json_data['message']['flags']):
                            self.memory.raiseEvent("TriggerGapFill", bool(json_data['message']['flags']['gap_fill']))
                elif(json_data['type'] == 'trigger'):
                    if('name' in json_data['message'] and 'status' in json_data['message']):
                        if(json_data['message']['name'] == 'Speech Recognition'):
                            self.memory.raiseEvent('ControlRecording', bool(json_data['message']['status']))
                elif(json_data['type'] == 'shortcut'):
                    if(json_data['message']):
                        self.memory.raiseEvent('StopAction', None)
                        self.memory.raiseEvent('Say', str(json_data['message']))
            except ValueError:
                data = response.decode('utf-8')
                print("Received non-JSON response:", data)
                if not data:
                    print("Data contains nothing, closing socket connection...")
                    self.client_socket.close()
                    self.connected = False
                    print("Connection Closed")

    def join(self, timeout=None):
        self.running = False
        self.client_socket.sendall('SHUTDOWN'.encode('utf-8'))
        self.client_socket.close()
        print("Connection closed")
        super(SocketClient, self).join(timeout)

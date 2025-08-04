import socket
import json
import threading
from naoqi import ALProxy
import time

class SocketClient(threading.Thread):
    def __init__(self, server_addr, server_port):
        super(SocketClient, self).__init__()
        self.server_addr = server_addr
        self.server_port = server_port
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connected = False
        self.running = True

        self.memory = ALProxy("ALMemory")

    def connection(self):
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((self.server_addr, self.server_port))
            self.connected = True

        except socket.error as e:
            print("Socket error:", e)
            self.client_socket.close()
            self.connected = False

    def run(self):
        buffer = ""
        while self.running:
            if not self.connected:
                self.connection()
                if not self.connected:
                    print("Connection refused, waiting to retry...")
                    time.sleep(5)  # Wait before retrying
                    continue
            try:
                response = self.client_socket.recv(4096)
                if not response:
                    self.connected = False
                    self.client_socket.close()
                    continue
                buffer += response.decode('utf-8')
                while True:
                    try:
                        json_data, index = json.JSONDecoder().raw_decode(buffer)
                        buffer = buffer[index:].lstrip()
                        if json_data.get('robot') in ['Haku', 'Pepper', '']:
                            self.process_message(json_data)
                    except ValueError:
                        break
            except socket.error as e:
                print("Socket error:", e)
                self.connected = False
                self.client_socket.close()
        if self.running:
            self.run()

    def process_message(self, json_data):
        print("Received message: {}".format(json_data))
        try:
            if json_data['type'] == 'script':
                msg = str(json_data['message'])
                if msg:
                    self.memory.raiseEvent('StopAction', None)
                    self.memory.raiseEvent('Say', msg)

            elif json_data['type'] == 'profile':
                if 'html' in json_data['message']:
                    self.memory.raiseEvent("LoadHTML", "http://198.18.0.1/apps/rmit-race/" + str(json_data['message']['html']))
                if 'flags' in json_data['message']:
                    if 'gap_fill' in json_data['message']['flags']:
                        self.memory.raiseEvent("TriggerGapFill", bool(json_data['message']['flags']['gap_fill']))
            elif json_data['type'] == 'trigger':
                if 'Signal' in json_data['message'] and 'Value' in json_data['message']:
                    signal = str(json_data['message']['Signal'])
                    value = json_data['message']['Value']
                    if signal is not None and value is not None:
                        self.memory.raiseEvent(signal, value)
            elif json_data['type'] == 'shortcut':
                if json_data['message']:
                    self.memory.raiseEvent('StopAction', None)
                    self.memory.raiseEvent('Say', str(json_data['message']))
            elif json_data['type'] == 'trigger-all':
                for item in json_data['message']:
                    if 'Signal' in item and 'Value' in item:
                        self.memory.raiseEvent(str(item['Signal']), item['Value'])
            elif json_data['type'] == 'Move':
                if json_data['message']:
                    key_press_data = json_data['message']
                    key_press_data = [str(key_press_data['key']), bool(key_press_data['holding'])]
                    self.memory.raiseEvent('Move', key_press_data)
            elif json_data['type'] == 'ConMove':
                if json_data['message']:
                    cont_move_data = json_data['message']
                    try:
                        x = float(cont_move_data['x'])
                        y = float(cont_move_data['y'])
                        hx = float(cont_move_data['hx'])
                        hy = float(cont_move_data['hy'])
                        cont_move_data = [x, y, hx, hy]
                        self.memory.raiseEvent('ContinuousMove', cont_move_data)
                    except (ValueError, TypeError) as e:
                        print("Error converting ConMove values to float: {}".format(e))
            elif json_data['type'] == 'announcement':
                if json_data['message']:
                    self.memory.raiseEvent('ChangeGreetingKey', str(json_data['message']))
        except Exception as e:
            print("ERROR: Processing message error {}".format(e))

    def join(self, timeout=None):
        self.running = False
        self.client_socket.sendall('SHUTDOWN'.encode('utf-8'))
        self.client_socket.close()
        print("Connection closed")
        super(SocketClient, self).join(timeout)

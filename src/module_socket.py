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
            print("Received something")
            # Split several truncated json messages but leave the full json message intact
            response = response.decode('utf-8').split('}{')
            response = [item + '}' if i != len(response) - 1 else item for i, item in enumerate(response)]
            response = ['{' + item if i != 0 else item for i, item in enumerate(response)]
            try:
                print("Received data {}".format(response))
                # loop through the json data and process each message
                for data in response:
                    json_data = json.loads(data.decode('utf-8'))
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
                        # print("Triggering event: ", json_data['message'])
                        if('Signal' in json_data['message'] and 'Value' in json_data['message']):
                            signal = str(json_data['message']['Signal'])
                            value = json_data['message']['Value']
                            # print("Signal: ", signal, "Value: ", value)
                            if signal is not None and value is not None:
                                self.memory.raiseEvent(signal, value)
                    elif(json_data['type'] == 'shortcut'):
                        if(json_data['message']):
                            self.memory.raiseEvent('StopAction', None)
                            self.memory.raiseEvent('Say', str(json_data['message']))
                    elif(json_data['type'] == 'trigger-all'):
                        # Recieved in format {type: "trigger-all", message: [{ Signal, Value }]}
                        for item in json_data['message']:
                            if('Signal' in item and 'Value' in item):
                                # print("Triggering event: ", item)
                                self.memory.raiseEvent(str(item['Signal']), item['Value'])
                    elif(json_data['type'] == 'Move'):
                        print(json_data['message'])
                        if json_data['message']:
                            key_press_data = json_data['message']
                            print("Received move event with value: {}".format(key_press_data))
                            # convert the key press data to an array [key, pressed]
                            key_press_data = [str(key_press_data['key'].decode('utf-8')), bool(key_press_data['holding'])]
                            print("Converted move event with value: {}".format(key_press_data))
                            self.memory.raiseEvent('Move', key_press_data)

            except ValueError:
                for data in response:
                    decoded_data = data.decode('utf-8')
                    print("Received non-JSON response: {}".format(decoded_data))
                    if not decoded_data:
                        print("Data contains nothing, closing socket connection...")
                        self.client_socket.close()
                        self.connected = False
                        print("Connection Closed")
                print("Received non-JSON response: {}".format(data))
                if not data:
                    print("Data contains nothing, closing socket connection...")
                    self.client_socket.close()
                    self.connected = False
                    print("Connection Closed")
            except Exception as e:
                print("ERROR: Socket decode error {}".format(e))

    def join(self, timeout=None):
        self.running = False
        self.client_socket.sendall('SHUTDOWN'.encode('utf-8'))
        self.client_socket.close()
        print("Connection closed")
        super(SocketClient, self).join(timeout)

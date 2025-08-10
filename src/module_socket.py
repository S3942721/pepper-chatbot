import socket
import json
import threading
from naoqi import ALProxy
import time
import struct
import numpy as np

class SocketClient(threading.Thread):
    def __init__(self, server_addr, server_port):
        super(SocketClient, self).__init__()
        self.server_addr = server_addr
        self.server_port = server_port
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connected = False
        self.running = True
        
        # Audio streaming variables
        self.audio_streaming_enabled = False
        self.audio_send_lock = threading.Lock()
        self.speech_module = None  # Direct reference to speech recognition module

        self.memory = ALProxy("ALMemory")

    def set_speech_module(self, speech_module):
        """Set reference to the speech recognition module"""
        self.speech_module = speech_module
        print("Speech module reference set in socket client")

    def connection(self):
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((self.server_addr, self.server_port))
            self.connected = True
            print("Socket connected to {}:{}".format(self.server_addr, self.server_port))

        except socket.error as e:
            print("Socket error:", e)
            self.client_socket.close()
            self.connected = False

    def enable_audio_streaming(self):
        """Enable audio streaming through the socket connection"""
        if not self.audio_streaming_enabled and self.speech_module:
            self.audio_streaming_enabled = True
            # Set this instance as the callback directly in the speech module
            self.speech_module.audioStreamCallback = self.send_audio_chunk
            self.speech_module.isStreamingEnabled = True
            self.speech_module.streamBuffer = []
            print("Audio streaming enabled via socket - callback set directly")
        elif not self.speech_module:
            print("ERROR: Speech module reference not set - cannot enable audio streaming")

    def disable_audio_streaming(self):
        """Disable audio streaming"""
        if self.audio_streaming_enabled and self.speech_module:
            self.audio_streaming_enabled = False
            self.speech_module.isStreamingEnabled = False
            self.speech_module.audioStreamCallback = None
            self.speech_module.streamBuffer = []
            print("Audio streaming disabled")

    def send_audio_chunk(self, audio_data):
        """Send audio chunk through socket with proper framing"""
        if not self.connected or not self.audio_streaming_enabled:
            print("DEBUG: Cannot send audio - connected: {}, streaming: {}".format(
                self.connected, self.audio_streaming_enabled))
            return
            
        try:
            with self.audio_send_lock:
                # Convert numpy array to bytes if needed
                if isinstance(audio_data, np.ndarray):
                    audio_bytes = audio_data.astype(np.int16).tostring()
                elif isinstance(audio_data, list):
                    # Convert list to numpy array then to bytes
                    audio_bytes = np.array(audio_data, dtype=np.int16).tostring()
                else:
                    print("ERROR: Unknown audio data type: {}".format(type(audio_data)))
                    return
                
                print("DEBUG: Sending audio chunk - {} bytes".format(len(audio_bytes)))
                
                # Create audio packet with header
                packet = {
                    'type': 'audio_stream',
                    'sample_rate': 48000,
                    'channels': 1,
                    'format': 'int16',
                    'data_length': len(audio_bytes)
                }
                
                # Send JSON header first
                header_json = json.dumps(packet) + '\n'
                self.client_socket.sendall(header_json.encode('utf-8'))
                
                # Send raw audio data
                self.client_socket.sendall(audio_bytes)
                print("DEBUG: Audio packet sent successfully")
                
        except socket.error as e:
            print("Error sending audio data: {}".format(e))
            self.connected = False
            self.disable_audio_streaming()
        except Exception as e:
            print("Unexpected error in send_audio_chunk: {}".format(e))

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
                self.disable_audio_streaming()
        if self.running:
            self.run()

    def process_message(self, json_data):
        print("Received message: {}".format(json_data))
        try:
            if json_data['type'] == 'enable_audio_stream':
                self.enable_audio_streaming()
            elif json_data['type'] == 'disable_audio_stream':
                self.disable_audio_streaming()
            elif json_data['type'] == 'script':
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
        self.disable_audio_streaming()
        self.client_socket.sendall('SHUTDOWN'.encode('utf-8'))
        self.client_socket.close()
        print("Connection closed")
        super(SocketClient, self).join(timeout)

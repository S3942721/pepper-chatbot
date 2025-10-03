#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Simple Audio Stream Test - saves received audio to WAV file
"""

import socket
import json
import wave
import time

def create_wav_file(filename, sample_rate=48000, channels=1):
    """Create a WAV file for writing audio data"""
    wav_file = wave.open(filename, 'wb')
    wav_file.setnchannels(channels)
    wav_file.setsampwidth(2)  # 16-bit
    wav_file.setframerate(sample_rate)
    return wav_file

def main():
    # Server configuration
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('0.0.0.0', 3456))
    server_socket.listen(1)
    
    print("Waiting for Pepper to connect on port 3456...")
    client_socket, addr = server_socket.accept()
    print("Connected to: {}".format(addr))
    
    # Create WAV file
    wav_file = create_wav_file('pepper_audio_stream.wav')
    
    try:
        # Enable audio streaming
        command = {"type": "enable_audio_stream", "robot": "Pepper"}
        client_socket.sendall((json.dumps(command) + '\n').encode('utf-8'))
        print("Audio streaming enabled. Recording for 30 seconds...")
        
        buffer = ""
        start_time = time.time()
        
        while time.time() - start_time < 30:  # Record for 30 seconds
            data = client_socket.recv(4096)
            if not data:
                break
                
            buffer += data.decode('utf-8', errors='ignore')
            
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                if line.strip():
                    try:
                        header = json.loads(line)
                        if header.get('type') == 'audio_stream':
                            data_length = header.get('data_length', 0)
                            if data_length > 0:
                                # Receive audio data
                                audio_data = b''
                                while len(audio_data) < data_length:
                                    chunk = client_socket.recv(data_length - len(audio_data))
                                    if not chunk:
                                        break
                                    audio_data += chunk
                                
                                # Write to WAV file
                                wav_file.writeframes(audio_data)
                                print("Received {} bytes of audio".format(len(audio_data)))
                    except ValueError:
                        pass
        
        # Disable streaming
        command = {"type": "disable_audio_stream", "robot": "Pepper"}
        client_socket.sendall((json.dumps(command) + '\n').encode('utf-8'))
        
    finally:
        wav_file.close()
        client_socket.close()
        server_socket.close()
        print("Audio saved to pepper_audio_stream.wav")

if __name__ == "__main__":
    main()

#!/usr/bin/env python

"""
Audio Stream Receiver for Pepper Robot
Connects to the Pepper robot's socket client and receives real-time audio stream
Requires: pip install pyaudio numpy
"""

import socket
import json
import threading
import time
import numpy as np
import argparse
import logging
import sys
try:
    import pyaudio
except ImportError:
    print("Error: PyAudio not installed. Please run: pip install pyaudio")
    exit(1)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('audio_receiver.log')
    ]
)
logger = logging.getLogger(__name__)

class AudioStreamReceiver:
    def __init__(self, host='0.0.0.0', port=3456, pepper_ip='192.168.1.100'):
        self.host = host
        self.port = port
        self.pepper_ip = pepper_ip
        self.server_socket = None
        self.client_socket = None
        self.running = False
        
        # Audio configuration (must match Pepper's settings)
        self.sample_rate = 48000
        self.channels = 1
        self.format = pyaudio.paInt16
        self.chunk_size = 4800  # 100ms at 48kHz
        
        logger.info(f"Audio config - Sample rate: {self.sample_rate}, Channels: {self.channels}, Chunk size: {self.chunk_size}")
        
        # PyAudio setup
        self.audio = pyaudio.PyAudio()
        self.stream = None
        
        # Threading
        self.receive_thread = None
        self.audio_enabled = False
        
        # Debug counters
        self.packets_received = 0
        self.bytes_played = 0

    def start_server(self):
        """Start the server and wait for Pepper to connect"""
        try:
            logger.info(f"Starting server on {self.host}:{self.port}")
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(1)
            
            logger.info(f"Server listening on {self.host}:{self.port}")
            logger.info("Waiting for Pepper robot to connect...")
            
            self.client_socket, addr = self.server_socket.accept()
            logger.info(f"Connected to Pepper robot at: {addr}")
            
            self.running = True
            return True
            
        except Exception as e:
            logger.error(f"Error starting server: {e}")
            return False

    def setup_audio_playback(self):
        """Initialize audio playback stream"""
        try:
            logger.info("Setting up audio playback...")
            
            # List available audio devices
            logger.debug("Available audio devices:")
            for i in range(self.audio.get_device_count()):
                info = self.audio.get_device_info_by_index(i)
                logger.debug(f"  Device {i}: {info['name']} - Max output channels: {info['maxOutputChannels']}")
            
            # Get default output device info
            default_device = self.audio.get_default_output_device_info()
            logger.info(f"Using default output device: {default_device['name']}")
            logger.info(f"Device sample rate: {default_device['defaultSampleRate']}")
            logger.info(f"Device channels: {default_device['maxOutputChannels']}")
            
            self.stream = self.audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                output=True,
                frames_per_buffer=self.chunk_size
            )
            
            logger.info("Audio playback stream initialized successfully")
            logger.debug(f"Stream info - Format: {self.format}, Channels: {self.channels}, Rate: {self.sample_rate}")
            
            # Test if stream is active
            if self.stream.is_active():
                logger.info("Audio stream is active and ready")
            else:
                logger.warning("Audio stream is not active!")
                
            return True
            
        except Exception as e:
            logger.error(f"Error setting up audio playback: {e}")
            return False

    def send_enable_audio_stream(self):
        """Send command to Pepper to enable audio streaming"""
        try:
            command = {
                "type": "enable_audio_stream",
                "robot": "Pepper"
            }
            message = json.dumps(command) + '\n'
            logger.debug(f"Sending command: {command}")
            self.client_socket.sendall(message.encode('utf-8'))
            logger.info("Audio stream enable command sent")
            return True
        except Exception as e:
            logger.error(f"Error sending enable command: {e}")
            return False

    def send_disable_audio_stream(self):
        """Send command to Pepper to disable audio streaming"""
        try:
            command = {
                "type": "disable_audio_stream",
                "robot": "Pepper"
            }
            message = json.dumps(command) + '\n'
            logger.debug(f"Sending command: {command}")
            self.client_socket.sendall(message.encode('utf-8'))
            logger.info("Audio stream disable command sent")
            return True
        except Exception as e:
            logger.error(f"Error sending disable command: {e}")
            return False

    def receive_audio_stream(self):
        """Receive and process audio stream from Pepper"""
        buffer = ""
        logger.info("Audio receive thread started")
        
        while self.running:
            try:
                # Receive data
                data = self.client_socket.recv(4096)
                if not data:
                    logger.warning("Connection closed by Pepper")
                    break
                
                logger.debug(f"Received {len(data)} bytes from socket")
                
                # Decode with error handling
                try:
                    decoded_data = data.decode('utf-8')
                except UnicodeDecodeError as e:
                    logger.warning(f"Unicode decode error: {e}, skipping this chunk")
                    continue
                    
                buffer += decoded_data
                
                # Process complete JSON messages
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line.strip():
                        try:
                            header = json.loads(line.strip())
                            logger.debug(f"Parsed JSON header: {header}")
                            
                            # Ensure header is a dictionary
                            if isinstance(header, dict):
                                if header.get('type') == 'audio_stream':
                                    self.handle_audio_packet(header)
                                else:
                                    logger.debug(f"Received non-audio message: {header}")
                            else:
                                logger.warning(f"Received non-dict JSON object: {type(header)} - {header}")
                                
                        except (ValueError, TypeError) as e:
                            # Not a JSON message, might be regular command response or corrupted data
                            logger.debug(f"JSON parsing error: {e}, line: {line[:50]}")
                            # Try to find if this is part of a larger message
                            if '{' in line or '}' in line:
                                logger.debug("Line contains JSON-like characters, might be fragmented")
                            
            except socket.error as e:
                logger.error(f"Socket error in receive thread: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected error in receive thread: {e}", exc_info=True)
                break
        
        logger.info("Audio receive thread ended")

    def handle_audio_packet(self, header):
        """Handle incoming audio packet"""
        try:
            # Validate header structure
            if not isinstance(header, dict):
                logger.error(f"Invalid header type: {type(header)}")
                return
                
            data_length = header.get('data_length', 0)
            sample_rate = header.get('sample_rate', 48000)
            channels = header.get('channels', 1)
            audio_format = header.get('format', 'int16')
            
            logger.debug(f"Audio packet - Length: {data_length}, Rate: {sample_rate}, Channels: {channels}, Format: {audio_format}")
            
            if data_length > 0:
                # Receive the raw audio bytes with timeout handling
                audio_data = b''
                start_time = time.time()
                timeout = 2.0  # 2 second timeout
                
                # Set socket timeout for receiving audio data
                original_timeout = self.client_socket.gettimeout()
                self.client_socket.settimeout(timeout)
                
                try:
                    while len(audio_data) < data_length:
                        remaining = data_length - len(audio_data)
                        chunk_size = min(remaining, 4096)
                        chunk = self.client_socket.recv(chunk_size)
                        
                        if not chunk:
                            logger.warning("Connection closed while receiving audio data")
                            break
                            
                        audio_data += chunk
                        logger.debug(f"Received audio chunk: {len(chunk)} bytes, total: {len(audio_data)}/{data_length}")
                        
                        # Check for timeout
                        if time.time() - start_time > timeout:
                            logger.warning(f"Timeout receiving audio data: {len(audio_data)}/{data_length} bytes received")
                            break
                            
                finally:
                    # Restore original socket timeout
                    self.client_socket.settimeout(original_timeout)
                
                receive_time = time.time() - start_time
                logger.debug(f"Audio data reception took {receive_time:.3f} seconds")
                
                if len(audio_data) == data_length:
                    if self.stream and self.stream.is_active():
                        logger.debug(f"Writing {len(audio_data)} bytes to audio stream")
                        
                        # Check for potential buffer issues
                        try:
                            available_frames = self.stream.get_write_available()
                            expected_frames = len(audio_data) // 2  # 16-bit samples
                            
                            if available_frames < expected_frames:
                                logger.warning(f"Audio buffer may be full: {available_frames} available, {expected_frames} needed")
                            
                            # Write to audio stream
                            play_start = time.time()
                            self.stream.write(audio_data)
                            play_time = time.time() - play_start
                            
                            self.packets_received += 1
                            self.bytes_played += len(audio_data)
                            
                            logger.info(f"Played audio chunk: {len(audio_data)} bytes (packet #{self.packets_received})")
                            logger.debug(f"Audio write took {play_time:.3f} seconds")
                            
                            # Calculate audio duration
                            samples = len(audio_data) // 2  # 16-bit samples
                            duration = samples / self.sample_rate
                            logger.debug(f"Audio chunk duration: {duration:.3f} seconds")
                            
                        except Exception as play_error:
                            logger.error(f"Error writing to audio stream: {play_error}")
                            
                    else:
                        logger.error("Audio stream is not available or not active")
                else:
                    logger.error(f"Incomplete audio data received: {len(audio_data)}/{data_length} bytes")
            else:
                logger.warning("Received audio packet with no data")
                    
        except Exception as e:
            logger.error(f"Error handling audio packet: {e}", exc_info=True)

    def run(self):
        """Main run loop"""
        logger.info("Starting audio stream receiver...")
        
        if not self.start_server():
            logger.error("Failed to start server")
            return
            
        if not self.setup_audio_playback():
            logger.error("Failed to setup audio playback")
            return
            
        # Start receiving thread
        logger.info("Starting receive thread...")
        self.receive_thread = threading.Thread(target=self.receive_audio_stream)
        self.receive_thread.daemon = True
        self.receive_thread.start()
        
        try:
            # Wait a moment for connection to stabilize
            logger.info("Waiting for connection to stabilize...")
            time.sleep(1)
            
            # Enable audio streaming
            if self.send_enable_audio_stream():
                logger.info("Audio streaming started. Press Ctrl+C to stop...")
                self.audio_enabled = True
                
                # Keep running until interrupted
                last_stats_time = time.time()
                while self.running:
                    time.sleep(1)
                    
                    # Print stats every 10 seconds
                    if time.time() - last_stats_time > 10:
                        logger.info(f"Stats - Packets received: {self.packets_received}, Total bytes played: {self.bytes_played}")
                        last_stats_time = time.time()
                        
            else:
                logger.error("Failed to enable audio streaming")
                
        except KeyboardInterrupt:
            logger.info("Shutdown requested by user")
            
        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up resources"""
        logger.info("Starting cleanup...")
        self.running = False
        
        if self.audio_enabled:
            logger.info("Disabling audio stream...")
            self.send_disable_audio_stream()
            
        if self.stream:
            logger.info("Stopping audio stream...")
            self.stream.stop_stream()
            self.stream.close()
            
        if self.audio:
            logger.info("Terminating PyAudio...")
            self.audio.terminate()
            
        if self.client_socket:
            logger.info("Closing client socket...")
            self.client_socket.close()
            
        if self.server_socket:
            logger.info("Closing server socket...")
            self.server_socket.close()
            
        logger.info(f"Final stats - Packets received: {self.packets_received}, Total bytes played: {self.bytes_played}")
        logger.info("Cleanup completed")

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Pepper Robot Audio Stream Receiver')
    parser.add_argument('--robot-ip', default='192.168.1.100', 
                        help='IP address of the Pepper robot (default: 192.168.1.100)')
    parser.add_argument('--host', default='0.0.0.0',
                        help='Host to listen on (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=3456,
                        help='Port to listen on (default: 3456)')
    parser.add_argument('--log-level', default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='Logging level (default: INFO)')
    
    args = parser.parse_args()
    
    # Set logging level
    logger.setLevel(getattr(logging, args.log_level))
    
    logger.info("Pepper Robot Audio Stream Receiver")
    logger.info("==================================")
    logger.info(f"Robot IP: {args.robot_ip}")
    logger.info(f"Listening on: {args.host}:{args.port}")
    logger.info(f"Log level: {args.log_level}")
    
    receiver = AudioStreamReceiver(host=args.host, port=args.port, pepper_ip=args.robot_ip)
    receiver.run()

if __name__ == "__main__":
    main()

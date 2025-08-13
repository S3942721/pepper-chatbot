# -*- coding: utf-8 -*-

import socket
import struct
import time
import numpy as np
from naoqi import ALModule, ALProxy
import traceback

SAMPLE_RATE = 16000  # Match external test settings
CHUNK_SIZE = 256     # Very small chunks (16ms at 16kHz)

class AudioStreamModule(ALModule):
    """
    Audio streaming module that captures audio from ALAudioDevice and streams via UDP
    using Pepper's microphones
    """

    def __init__(self, strModuleName, strNaoIp, port, target_host, target_port):
        try:
            ALModule.__init__(self, strModuleName)
            
            self.BIND_PYTHON(self.getName(), "callback")
            self.strNaoIp = strNaoIp
            self.port = port
            
            # Network settings
            self.target_host = target_host
            self.target_port = target_port
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sequence = 0
            
            # Audio streaming state
            self.isStarted = False
            self.isStreamingEnabled = False
            
            # Audio buffer for chunking
            self.audioBuffer = []
            self.bufferSize = CHUNK_SIZE
            
            # Memory setup
            self.memory = ALProxy("ALMemory", self.strNaoIp, self.port)
            self.memory.subscribeToEvent("ControlUDPAudioStreaming", self.getName(), "control_streaming")
            
            print("AudioStreamModule initialized - target: {}:{}".format(target_host, target_port))
            
        except BaseException as err:
            print("ERR: AudioStreamModule: loading error: %s" % str(err))

    def __del__(self):
        print("INF: AudioStreamModule.__del__: cleaning everything")
        self.stop()
        if hasattr(self, 'sock'):
            self.sock.close()

    def start(self):
        """Start audio capture from ALAudioDevice"""
        if self.isStarted:
            return
            
        print("INF: AudioStreamModule: starting audio capture")
        self.isStarted = True
        
        try:
            audio = ALProxy("ALAudioDevice", self.strNaoIp, self.port)
            nNbrChannelFlag = 0  # ALL_Channels
            nDeinterleave = 0
            audio.setClientPreferences(self.getName(), SAMPLE_RATE, nNbrChannelFlag, nDeinterleave)
            audio.subscribe(self.getName())
        except Exception as e:
            print("ERR: Failed to start audio capture: %s" % str(e))
            self.isStarted = False

    def stop(self):
        """Stop audio capture"""
        if not self.isStarted:
            return
            
        print("INF: AudioStreamModule: stopping audio capture")
        self.isStarted = False
        
        try:
            audio = ALProxy("ALAudioDevice", self.strNaoIp, self.port)
            audio.unsubscribe(self.getName())
        except Exception as e:
            print("ERR: Failed to stop audio capture: %s" % str(e))

    def control_streaming(self, _, value):
        """Control UDP audio streaming based on boolean value"""
        if value:
            self.enable_stream()
        else:
            self.disable_stream()

    def enable_stream(self):
        """Enable UDP audio streaming"""
        if self.isStreamingEnabled:
            return
            
        self.isStreamingEnabled = True
        self.sequence = 0
        self.audioBuffer = []
        print("INF: UDP Audio streaming enabled")
        
        # Start audio capture if not already started
        if not self.isStarted:
            self.start()

    def disable_stream(self):
        """Disable UDP audio streaming"""
        if not self.isStreamingEnabled:
            return
            
        self.isStreamingEnabled = False
        self.audioBuffer = []
        print("INF: UDP Audio streaming disabled")

    def processRemote(self, nbOfChannels, nbrOfSamplesByChannel, aTimeStamp, buffer):
        """Process audio data from ALAudioDevice"""
        if not self.isStreamingEnabled:
            return
            
        try:
            # Convert audio buffer to numpy array
            aSoundDataInterlaced = np.fromstring(str(buffer), dtype=np.int16)
            aSoundData = np.reshape(aSoundDataInterlaced, (nbOfChannels, nbrOfSamplesByChannel), 'F')
            
            # Use front microphone (channel 0) - downsample from 48kHz to 16kHz
            frontMicData = aSoundData[0]
            
            # Simple downsampling by taking every 3rd sample (48000/16000 = 3)
            downsampledData = frontMicData[::3]
            
            # Add to buffer
            self.audioBuffer.extend(downsampledData)
            
            # Send chunks when buffer is large enough
            while len(self.audioBuffer) >= self.bufferSize:
                chunk = self.audioBuffer[:self.bufferSize]
                self.audioBuffer = self.audioBuffer[self.bufferSize:]
                
                self.send_audio_chunk(chunk)
                
        except Exception as e:
            print("ERR: AudioStreamModule processRemote error: %s" % str(e))
            traceback.print_exc()

    def send_audio_chunk(self, audio_data):
        """Send audio chunk via UDP - matches externalAudioStreamTest.py format"""
        try:
            # Convert to int16 array for volume calculation
            audio_array = np.array(audio_data, dtype=np.int16)
            
            # Calculate volume level
            volume = int(np.max(np.abs(audio_array))) if len(audio_array) > 0 else 0
            
            # Create timestamp (microseconds)
            timestamp = int(time.time() * 1000000) & 0xFFFFFFFF  # Keep only lower 32 bits
            volume = max(0, min(4294967295, abs(volume)))  # Clamp to valid range
            
            # Convert audio data to bytes
            audio_bytes = audio_array.astype(np.int16).tostring()
            
            # Create packet: sequence + timestamp + volume + audio data
            packet = struct.pack('!III', self.sequence, timestamp, volume) + audio_bytes
            
            # Send UDP packet
            self.sock.sendto(packet, (self.target_host, self.target_port))
            self.sequence += 1
            
            # Print volume indicator every 50 packets (~800ms at 16ms chunks)
            if self.sequence % 50 == 0:
                volume_bar = '#' * min(20, volume // 1000)
                print("Volume: [{}{}] {} (seq: {})".format(
                    volume_bar, 
                    ' ' * (20 - len(volume_bar)), 
                    volume,
                    self.sequence
                ))
                
        except Exception as e:
            print("ERR: Failed to send audio chunk: %s" % str(e))

    def set_target(self, host, port):
        """Change target host and port for streaming"""
        self.target_host = host
        self.target_port = port
        print("INF: Audio stream target changed to {}:{}".format(host, port))

    def get_sequence(self):
        """Get current sequence number"""
        return self.sequence

    def get_streaming_status(self):
        """Get current streaming status"""
        return {
            'streaming': self.isStreamingEnabled,
            'started': self.isStarted,
            'sequence': self.sequence,
            'target': "{}:{}".format(self.target_host, self.target_port),
            'buffer_size': len(self.audioBuffer)
        }

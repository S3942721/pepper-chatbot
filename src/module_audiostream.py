# -*- coding: utf-8 -*-

import socket
import struct
import time
import numpy as np
from naoqi import ALModule, ALProxy
import traceback

# Audio streaming constants - CRITICAL for proper audio quality
SAMPLE_RATE = 16000  # Hz - Must be exactly 16kHz for web client
CHUNK_SIZE = 256     # samples per packet (16ms duration at 16kHz)
PACKET_INTERVAL = 0.016  # seconds (16ms) - consistent timing crucial
TARGET_PACKET_SIZE = 524  # 12 byte header + 512 byte audio data

class AudioStreamModule(ALModule):
    """
    Audio streaming module that captures audio from ALAudioDevice and streams via UDP
    using Pepper's microphones with proper audio processing for high quality streaming
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
            
            # Network logging variables
            self.packets_sent = 0
            self.bytes_sent = 0
            self.last_network_log_time = time.time()
            self.network_errors = 0
            
            print("NETWORK: Creating UDP socket for {}:{}".format(target_host, target_port))
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
            # Test socket connectivity
            try:
                print("NETWORK: Testing UDP socket connectivity...")
                test_packet = b"TEST_PACKET"
                self.sock.sendto(test_packet, (self.target_host, self.target_port))
                print("NETWORK: UDP socket test successful - sent {} bytes to {}:{}".format(
                    len(test_packet), self.target_host, self.target_port))
            except Exception as e:
                print("NETWORK: UDP socket test failed: {}".format(e))
                self.network_errors += 1
            
            self.sequence = 0
            
            # Audio streaming state
            self.isStarted = False
            self.isStreamingEnabled = False
            
            # Audio buffer for chunking - exactly 256 samples per packet
            self.audioBuffer = []
            self.bufferSize = CHUNK_SIZE
            
            # Audio processing counters
            self.audio_chunks_processed = 0
            self.audio_samples_processed = 0
            
            # Precise timing for consistent packet intervals
            self.last_packet_time = 0.0
            self.timing_errors = 0
            self.packets_skipped = 0
            
            # Anti-aliasing filter state for proper downsampling
            # Simple IIR filter coefficients to avoid scipy dependency
            self.filter_history = [0.0, 0.0, 0.0]  # Keep last 3 samples for simple filter
            
            # Memory setup
            self.memory = ALProxy("ALMemory", self.strNaoIp, self.port)
            self.memory.subscribeToEvent("ControlUDPAudioStreaming", self.getName(), "control_streaming")
            
            print("AudioStreamModule initialized with high-quality audio processing - target: {}:{}".format(target_host, target_port))
            
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
        print("CONTROL: UDP audio streaming control signal received - value: {}".format(value))
        if value:
            self.enable_stream()
        else:
            self.disable_stream()

    def enable_stream(self):
        """Enable UDP audio streaming with timing reset"""
        if self.isStreamingEnabled:
            print("CONTROL: UDP audio streaming already enabled")
            return
            
        self.isStreamingEnabled = True
        self.sequence = 0
        self.audioBuffer = []
        
        # Reset timing and counters
        self.last_packet_time = time.time()
        self.packets_sent = 0
        self.bytes_sent = 0
        self.network_errors = 0
        self.audio_chunks_processed = 0
        self.audio_samples_processed = 0
        self.timing_errors = 0
        self.packets_skipped = 0
        self.last_network_log_time = time.time()
        
        # Reset filter state
        self.filter_history = [0.0, 0.0, 0.0]
        
        print("CONTROL: UDP Audio streaming ENABLED - target: {}:{} (16kHz, 16ms packets)".format(
            self.target_host, self.target_port))
        
        # Start audio capture if not already started
        if not self.isStarted:
            self.start()

    def disable_stream(self):
        """Disable UDP audio streaming with comprehensive statistics"""
        if not self.isStreamingEnabled:
            print("CONTROL: UDP audio streaming already disabled")
            return
            
        self.isStreamingEnabled = False
        self.audioBuffer = []
        
        # Reset filter state
        self.filter_history = [0.0, 0.0, 0.0]
        
        # Print comprehensive final statistics
        elapsed_time = time.time() - self.last_network_log_time
        print("STATS: UDP streaming session ended:")
        print("  - Duration: {:.2f} seconds".format(elapsed_time))
        print("  - Packets sent: {}".format(self.packets_sent))
        print("  - Packets skipped: {}".format(self.packets_skipped))
        print("  - Bytes sent: {}".format(self.bytes_sent))
        print("  - Audio chunks processed: {}".format(self.audio_chunks_processed))
        print("  - Audio samples processed: {}".format(self.audio_samples_processed))
        print("  - Network errors: {}".format(self.network_errors))
        print("  - Timing errors: {}".format(self.timing_errors))
        if elapsed_time > 0:
            expected_packets = int(elapsed_time / PACKET_INTERVAL)
            packet_accuracy = (float(self.packets_sent) / expected_packets * 100) if expected_packets > 0 else 0
            print("  - Expected packets: {}, Accuracy: {:.1f}%".format(expected_packets, packet_accuracy))
            print("  - Average rate: {:.2f} packets/sec, {:.2f} KB/sec".format(
                self.packets_sent / elapsed_time, (self.bytes_sent / elapsed_time) / 1024))
        
        print("CONTROL: UDP Audio streaming DISABLED")

    def apply_simple_lowpass_filter(self, data):
        """Apply simple anti-aliasing filter before downsampling (Python 2.7 compatible)"""
        try:
            # Convert to float for filtering
            data_float = data.astype(np.float32)
            filtered_data = np.zeros_like(data_float)
            
            # Simple 3-tap FIR filter to reduce aliasing
            # Coefficients for basic low-pass filter
            a0, a1, a2 = 0.25, 0.5, 0.25
            
            for i in range(len(data_float)):
                if i == 0:
                    # Use history for first sample
                    filtered_data[i] = (a0 * self.filter_history[2] + 
                                      a1 * self.filter_history[1] + 
                                      a2 * data_float[i])
                elif i == 1:
                    filtered_data[i] = (a0 * self.filter_history[1] + 
                                      a1 * data_float[i-1] + 
                                      a2 * data_float[i])
                else:
                    filtered_data[i] = (a0 * data_float[i-2] + 
                                      a1 * data_float[i-1] + 
                                      a2 * data_float[i])
            
            # Update filter history for next call
            if len(data_float) >= 2:
                self.filter_history = [data_float[-2], data_float[-1], data_float[-1]]
            elif len(data_float) == 1:
                self.filter_history = [self.filter_history[1], self.filter_history[2], data_float[0]]
            
            return filtered_data.astype(np.int16)
            
        except Exception as e:
            print("WARN: Filter error, using unfiltered data: {}".format(e))
            return data

    def proper_downsample_48k_to_16k(self, audio_48k):
        """Properly downsample from 48kHz to 16kHz with anti-aliasing"""
        try:
            # Apply anti-aliasing filter first
            filtered_data = self.apply_simple_lowpass_filter(audio_48k)
            
            # Downsample by factor of 3 (48000/16000 = 3)
            downsampled = filtered_data[::3]
            
            # Ensure proper int16 range
            downsampled = np.clip(downsampled, -32768, 32767).astype(np.int16)
            
            return downsampled
            
        except Exception as e:
            print("ERR: Downsampling failed: {}".format(e))
            # Fallback to simple decimation if filter fails
            return audio_48k[::3].astype(np.int16)

    def processRemote(self, nbOfChannels, nbrOfSamplesByChannel, aTimeStamp, buffer):
        """Process audio data with proper timing and high-quality downsampling"""
        if not self.isStreamingEnabled:
            return
            
        try:
            # Convert audio buffer to numpy array
            aSoundDataInterlaced = np.fromstring(str(buffer), dtype=np.int16)
            aSoundData = np.reshape(aSoundDataInterlaced, (nbOfChannels, nbrOfSamplesByChannel), 'F')
            
            # Use front microphone (channel 0)
            frontMicData = aSoundData[0]
            
            # Proper downsampling from 48kHz to 16kHz with anti-aliasing
            downsampledData = self.proper_downsample_48k_to_16k(frontMicData)
            
            # Add to buffer
            self.audioBuffer.extend(downsampledData)
            self.audio_samples_processed += len(downsampledData)
            
            # Send packets based on precise timing rather than just buffer availability
            current_time = time.time()
            time_since_last_packet = current_time - self.last_packet_time
            
            # Send packet if we have enough data AND enough time has passed
            if (len(self.audioBuffer) >= self.bufferSize and 
                time_since_last_packet >= PACKET_INTERVAL):
                
                chunk = self.audioBuffer[:self.bufferSize]
                self.audioBuffer = self.audioBuffer[self.bufferSize:]
                
                self.send_audio_packet_with_timing(chunk, current_time)
                self.audio_chunks_processed += 1
                
            elif time_since_last_packet >= (PACKET_INTERVAL * 1.5):
                # We're behind schedule - send partial packet or skip
                if len(self.audioBuffer) >= self.bufferSize // 2:
                    # Send partial packet padded with zeros
                    chunk = self.audioBuffer[:self.bufferSize]
                    if len(chunk) < self.bufferSize:
                        # Pad with zeros to maintain packet size
                        padding = np.zeros(self.bufferSize - len(chunk), dtype=np.int16)
                        chunk = np.concatenate([chunk, padding])
                    
                    self.audioBuffer = self.audioBuffer[len(self.audioBuffer[:self.bufferSize]):]
                    self.send_audio_packet_with_timing(chunk, current_time)
                    self.audio_chunks_processed += 1
                else:
                    # Skip this packet interval
                    self.packets_skipped += 1
                    self.last_packet_time = current_time
            
            # Debug logging every 100 chunks (~1.6 seconds)
            if self.audio_chunks_processed % 100 == 0 and self.audio_chunks_processed > 0:
                print("AUDIO: Processed {} chunks, {} samples, buffer: {}, timing errors: {}, skipped: {}".format(
                    self.audio_chunks_processed, self.audio_samples_processed, 
                    len(self.audioBuffer), self.timing_errors, self.packets_skipped))
                
        except Exception as e:
            print("ERR: AudioStreamModule processRemote error: %s" % str(e))
            traceback.print_exc()

    def send_audio_packet_with_timing(self, audio_data, send_time):
        """Send properly formatted UDP packet with exact specifications"""
        try:
            # Ensure exactly 256 samples
            audio_array = np.array(audio_data, dtype=np.int16)
            if len(audio_array) != CHUNK_SIZE:
                print("WARN: Audio chunk size mismatch: expected {}, got {}".format(
                    CHUNK_SIZE, len(audio_array)))
                # Pad or truncate to exact size
                if len(audio_array) < CHUNK_SIZE:
                    padding = np.zeros(CHUNK_SIZE - len(audio_array), dtype=np.int16)
                    audio_array = np.concatenate([audio_array, padding])
                else:
                    audio_array = audio_array[:CHUNK_SIZE]
            
            # Validate audio data range
            audio_array = np.clip(audio_array, -32768, 32767)
            
            # Calculate RMS volume for better representation
            if len(audio_array) > 0:
                rms = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))
                volume = int(min(32767, rms * 10))  # Scale and clamp
            else:
                volume = 0
            
            # Create timestamp (microseconds, 32-bit)
            timestamp = int(send_time * 1000000) & 0xFFFFFFFF
            
            # Create packet header (big-endian for network)
            header = struct.pack('!III', self.sequence, timestamp, volume)
            
            # Convert audio to bytes (little-endian int16 for audio data)
            # Use tostring() for Python 2.7 compatibility
            audio_bytes = audio_array.astype('<i2').tostring()
            
            # Verify packet format
            if len(header) != 12:
                print("ERR: Header size incorrect: {} bytes".format(len(header)))
                return
            if len(audio_bytes) != 512:
                print("ERR: Audio data size incorrect: {} bytes (expected 512)".format(len(audio_bytes)))
                return
            
            # Create complete packet
            packet = header + audio_bytes
            
            # Verify total packet size
            if len(packet) != TARGET_PACKET_SIZE:
                print("ERR: Total packet size incorrect: {} bytes (expected {})".format(
                    len(packet), TARGET_PACKET_SIZE))
                return
            
            # Send UDP packet
            try:
                bytes_sent = self.sock.sendto(packet, (self.target_host, self.target_port))
                
                if bytes_sent != len(packet):
                    print("NETWORK: WARNING - Partial send: {} of {} bytes".format(
                        bytes_sent, len(packet)))
                
                # Update timing and counters
                self.last_packet_time = send_time
                self.packets_sent += 1
                self.bytes_sent += bytes_sent
                
                # Detailed logging every 10 packets
                if self.sequence % 10 == 0:
                    print("PACKET: #{} -> {}:{} | {}B | vol:{} | ts:{} | time:{:.3f}s".format(
                        self.sequence, self.target_host, self.target_port, len(packet),
                        volume, timestamp, send_time))
                
                # Network stats every 50 packets
                if self.sequence % 50 == 0:
                    elapsed = send_time - self.last_network_log_time
                    if elapsed > 0:
                        actual_rate = 50.0 / elapsed
                        expected_rate = 1.0 / PACKET_INTERVAL
                        rate_accuracy = (actual_rate / expected_rate * 100)
                        print("NETWORK: Rate {:.1f}/{:.1f} pkt/s ({:.1f}%) | {} pkts | {:.1f} KB | {} errs".format(
                            actual_rate, expected_rate, rate_accuracy, self.packets_sent, 
                            self.bytes_sent / 1024.0, self.network_errors))
                    self.last_network_log_time = send_time
                
            except socket.error as e:
                self.network_errors += 1
                print("NETWORK: Socket error #{}: {}".format(self.network_errors, e))
                
                # Recreate socket after multiple errors
                if self.network_errors % 10 == 0:
                    print("NETWORK: Recreating socket after {} errors".format(self.network_errors))
                    try:
                        self.sock.close()
                        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        print("NETWORK: Socket recreated successfully")
                    except Exception as recreate_error:
                        print("NETWORK: Failed to recreate socket: {}".format(recreate_error))
            
            self.sequence += 1
            
            # Volume display every 50 packets
            if self.sequence % 50 == 0:
                volume_bar = '#' * min(20, volume // 1000)
                print("Volume: [{}{}] {} RMS (seq: {})".format(
                    volume_bar, ' ' * (20 - len(volume_bar)), volume, self.sequence))
                
        except Exception as e:
            print("ERR: Failed to send audio packet: %s" % str(e))
            traceback.print_exc()

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

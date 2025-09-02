# -*- coding: utf-8 -*-

import sys
import time
import socket
import numpy as np
from naoqi import ALModule, ALProxy
import traceback
import logger

# Don't import GStreamer at module level - it intercepts command line arguments
# We'll import it only when needed in the methods

# Audio streaming constants
SAMPLE_RATE = 16000  # Hz - 16kHz for audio streaming
CHUNK_SIZE = 256     # samples per packet (16ms duration at 16kHz)

class AudioStreamModule(ALModule):
    """
    Audio streaming module using GStreamer pipeline for real-time audio transmission
    Simple and efficient approach similar to pepper_audio_sender
    """

    def __init__(self, strModuleName, strNaoIp, port, target_host, target_port):
        
        self.led_service = ALProxy('ALLeds')
        try:
            ALModule.__init__(self, strModuleName)
            
            self.BIND_PYTHON(self.getName(), "callback")
            self.strNaoIp = strNaoIp
            self.port = port
            
            # Network settings
            self.target_host = target_host
            self.target_port = target_port
            
            # GStreamer pipeline
            self.pipeline = None
            self.gstreamer_available = None  # Lazy check
            
            # Audio streaming state
            self.isStarted = False
            self.isStreamingEnabled = False
            self.isSpeaking = False  # Track speaking state
            
            # Statistics
            self.stream_start_time = 0
            self.packets_sent = 0
            self.network_errors = 0
            
            logger.info("AudioStreamModule initialized - target:", target_host, target_port)
            
            # Memory setup
            self.memory = ALProxy("ALMemory", self.strNaoIp, self.port)
            self.memory.subscribeToEvent("ControlAudioStreaming", self.getName(), "control_streaming")
            self.memory.subscribeToEvent("Speaking", self.getName(), "on_speaking_event")
            
        except BaseException as err:
            logger.error("AudioStreamModule: loading error:", err)

    def check_gstreamer_availability(self):
        """Check if GStreamer is available - only when needed"""
        if self.gstreamer_available is not None:
            return self.gstreamer_available
            
        try:
            # Add GStreamer path for Python 2.7
            sys.path.append('/usr/lib/python2.7/site-packages/gst-0.10')
            
            import gst
            import gobject
            gobject.threads_init()
            
            # Store references for later use
            self.gst = gst
            self.gobject = gobject
            self.gstreamer_available = True
            
            logger.info("GStreamer available")
            return True
            
        except ImportError as e:
            logger.warning("GStreamer not available:", e)
            self.gstreamer_available = False
            return False

    def create_gstreamer_pipeline(self):
        """Create GStreamer pipeline for audio streaming"""
        if not self.check_gstreamer_availability():
            logger.error("Cannot create pipeline - GStreamer not available")
            return False
            
        try:
            # Create GStreamer pipeline description
            pipeline_desc = (
                "alsasrc device=default "
                "blocksize=4096 "
                "latency-time=30000 ! "  # 30ms latency
                "audio/x-raw-int,rate=44100,channels=1,width=16,depth=16 ! "
                "audioconvert ! "
                "queue "
                "max-size-buffers=20 "
                "max-size-time=300000000 "
                "leaky=downstream ! "
                "rtpL16pay "
                "mtu=1200 "
                "pt=96 ! "
                "udpsink host=%s port=%d "
                "sync=false "
                "async=false"
            ) % (self.target_host, self.target_port)
            
            logger.info("Creating GStreamer pipeline:", pipeline_desc)
            
            self.pipeline = self.gst.parse_launch(pipeline_desc)
            
            # Set up message handling
            bus = self.pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect("message", self.on_gstreamer_message)
            
            return True
            
        except Exception as e:
            logger.error("Failed to create GStreamer pipeline:", e)
            logger.error("Trying simple fallback pipeline...")
            
            # Fallback: even simpler pipeline if the main one fails
            try:
                fallback_pipeline_desc = (
                    "alsasrc ! "
                    "audioconvert ! "
                    "rtpL16pay ! "
                    "udpsink host=%s port=%d"
                ) % (self.target_host, self.target_port)
                
                logger.info("Trying fallback pipeline:", fallback_pipeline_desc)
                
                self.pipeline = self.gst.parse_launch(fallback_pipeline_desc)
                
                # Set up message handling
                bus = self.pipeline.get_bus()
                bus.add_signal_watch()
                bus.connect("message", self.on_gstreamer_message)
                
                return True
                
            except Exception as e2:
                logger.error("All pipeline attempts failed:", e2)
                return False

    def on_gstreamer_message(self, bus, message):
        """Handle GStreamer pipeline messages"""
        if message.type == self.gst.MESSAGE_ERROR:
            err, debug = message.parse_error()
            logger.error("GStreamer error:", err)
            logger.error("Debug:", debug)
            self.network_errors += 1
            self.stop_gstreamer_pipeline()
        elif message.type == self.gst.MESSAGE_EOS:
            logger.info("End of stream")
            self.stop_gstreamer_pipeline()
        elif message.type == self.gst.MESSAGE_STATE_CHANGED:
            old_state, new_state, pending_state = message.parse_state_changed()
            if message.src == self.pipeline:
                logger.info("Pipeline state changed from", old_state.value_name, "to", new_state.value_name)

    def start_gstreamer_pipeline(self):
        """Start the GStreamer audio pipeline"""
        if not self.check_gstreamer_availability():
            logger.error("Cannot start pipeline - GStreamer not available")
            return False
            
        if not self.pipeline:
            if not self.create_gstreamer_pipeline():
                return False
        
        try:
            logger.info("Starting GStreamer pipeline to", self.target_host, self.target_port)
            self.pipeline.set_state(self.gst.STATE_PLAYING)
            self.stream_start_time = time.time()
            return True
        except Exception as e:
            logger.error("Failed to start GStreamer pipeline:", e)
            return False

    def stop_gstreamer_pipeline(self):
        """Stop the GStreamer audio pipeline"""
        if self.pipeline and self.gstreamer_available:
            try:
                self.pipeline.set_state(self.gst.STATE_NULL)
                
                # Print session statistics
                if self.stream_start_time > 0:
                    duration = time.time() - self.stream_start_time
                    logger.info("Streaming session ended:")
                    logger.info("  - Duration:", duration, "seconds")
                    logger.info("  - Target:", self.target_host, ":", self.target_port)
                    logger.info("  - Network errors:", self.network_errors)
                
                self.pipeline = None
                self.stream_start_time = 0
                
            except Exception as e:
                logger.error("Failed to stop GStreamer pipeline:", e)

    def test_network_connection(self):
        """Test if target device is reachable"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(1)
            sock.sendto("test", (self.target_host, self.target_port))
            sock.close()
            return True
        except:
            return False

    def control_streaming(self, _, value):
        """Control audio streaming based on boolean value"""
        logger.info("CONTROL: Audio streaming control signal received - value:", value)
        if value:
            self.enable_stream()
        else:
            self.disable_stream()

    def on_speaking_event(self, _, is_speaking):
        """Handle speaking state changes from centralized speaking manager"""
        is_speaking = bool(is_speaking)
        
        logger.info("Speaking event received from speaking manager - value:", is_speaking)
        
        # Only process if state actually changed
        if self.isSpeaking != is_speaking:
            self.isSpeaking = is_speaking
            
            if self.isSpeaking:
                logger.info("Speaking detected - pausing audio stream")
                self.led_service.fadeRGB("FaceLeds", 0xFF0000, 0.1)
                
                # Pause the pipeline if streaming is enabled
                if self.pipeline and self.gstreamer_available and self.isStreamingEnabled:
                    try:
                        self.pipeline.set_state(self.gst.STATE_PAUSED)
                        logger.info("Pipeline paused successfully")
                    except Exception as e:
                        logger.error("Failed to pause GStreamer pipeline:", e)
            else:
                logger.info("Speaking ended - resuming audio stream")
                self.resume_audio_stream()
        else:
            logger.debug("Speaking state unchanged, no action needed")

    def resume_audio_stream(self):
        """Resume audio streaming after speaking ends"""
        try:
            self.led_service.fadeRGB("FaceLeds", 0x00FF00, 0.1)
            
            if self.pipeline and self.gstreamer_available and self.isStreamingEnabled:
                try:
                    # Resume the pipeline
                    self.pipeline.set_state(self.gst.STATE_PLAYING)
                    logger.info("Pipeline resumed successfully")
                except Exception as e:
                    logger.error("Failed to resume GStreamer pipeline:", e)
        except Exception as e:
            logger.error("Error in resume_audio_stream:", e)

    def enable_stream(self):
        """Enable audio streaming using GStreamer"""
        if self.isStreamingEnabled:
            logger.info("CONTROL: Audio streaming already enabled")
            return
            
        if not self.check_gstreamer_availability():
            logger.error("Cannot enable streaming - GStreamer not available")
            return
        
        # Test network connectivity
        logger.info("Testing network connectivity to ", self.target_host, ":", self.target_port)
        if not self.test_network_connection():
            logger.warning("Network connectivity test failed")
        else:
            logger.info("Network connectivity test successful")
        
        # Start GStreamer pipeline
        if self.start_gstreamer_pipeline():
            self.isStreamingEnabled = True
            self.network_errors = 0
            
            # If currently speaking, start in paused state
            if self.isSpeaking:
                logger.info("Starting in paused state due to active speaking")
                try:
                    self.pipeline.set_state(self.gst.STATE_PAUSED)
                except Exception as e:
                    logger.error("Failed to pause pipeline on start:", e)
            
            logger.info("CONTROL: Audio streaming ENABLED -", self.target_host, self.target_port, "(GStreamer RTP/L16)")
        else:
            logger.error("Failed to enable audio streaming")

    def disable_stream(self):
        """Disable audio streaming"""
        if not self.isStreamingEnabled:
            logger.info("CONTROL: Audio streaming already disabled")
            return
            
        self.isStreamingEnabled = False
        self.stop_gstreamer_pipeline()
        logger.info("CONTROL: Audio streaming DISABLED")

    def set_target(self, host, port):
        """Change target host and port for streaming"""
        was_streaming = self.isStreamingEnabled
        
        if was_streaming:
            self.disable_stream()
        
        self.target_host = host
        self.target_port = port
        logger.info("Audio stream target changed to", host, port)
        
        if was_streaming:
            self.enable_stream()

    def get_streaming_status(self):
        """Get current streaming status including speaking state"""
        return {
            'streaming': self.isStreamingEnabled,
            'speaking': self.isSpeaking,
            'gstreamer_available': self.check_gstreamer_availability(),
            'target': "{}:{}".format(self.target_host, self.target_port),
            'network_errors': self.network_errors,
            'format': 'RTP/L16' if self.check_gstreamer_availability() else 'unavailable'
        }

    def get_streaming_status(self):
        """Get current streaming status"""
        return {
            'streaming': self.isStreamingEnabled,
            'gstreamer_available': self.check_gstreamer_availability(),
            'target': "{}:{}".format(self.target_host, self.target_port),
            'network_errors': self.network_errors,
            'format': 'RTP/L16' if self.check_gstreamer_availability() else 'unavailable'
        }

    def downsample_48k_to_16k(self, audio_48k):
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
            logger.error("Downsampling failed:", e)
            # Fallback to simple decimation if filter fails
            return audio_48k[::3].astype(np.int16)

    def processRemote(self, nbOfChannels, nbrOfSamplesByChannel, aTimeStamp, buffer):
        """Process audio data with RTP streaming and proper timing"""
        if not self.isStreamingEnabled:
            return
            
        try:
            # Convert audio buffer to numpy array
            aSoundDataInterlaced = np.fromstring(str(buffer), dtype=np.int16)
            aSoundData = np.reshape(aSoundDataInterlaced, (nbOfChannels, nbrOfSamplesByChannel), 'F')
            
            # Use front microphone (channel 0)
            frontMicData = aSoundData[0]
            
            # Proper downsampling from 48kHz to 16kHz with anti-aliasing
            downsampledData = self.downsample_48k_to_16k(frontMicData)
            
            # Add to buffer
            self.audioBuffer.extend(downsampledData)
            self.audio_samples_processed += len(downsampledData)
            
            # Send RTP packets based on precise timing
            current_time = time.time()
            time_since_last_packet = current_time - self.last_packet_time
            
            # Send packet if we have enough data AND enough time has passed
            if (len(self.audioBuffer) >= self.bufferSize and 
                time_since_last_packet >= PACKET_INTERVAL):
                
                chunk = self.audioBuffer[:self.bufferSize]
                self.audioBuffer = self.audioBuffer[self.bufferSize:]
                
                self.send_rtp_audio_packet(chunk, current_time)
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
                    self.send_rtp_audio_packet(chunk, current_time)
                    self.audio_chunks_processed += 1
                else:
                    # Skip this packet interval
                    self.packets_skipped += 1
                    self.last_packet_time = current_time
            
            # Debug logging every 100 chunks (~1.6 seconds)
            if self.audio_chunks_processed % 100 == 0 and self.audio_chunks_processed > 0:
                logger.debug("Processed", self.audio_chunks_processed, "chunks, ", self.audio_samples_processed,
                             "samples, buffer: ", len(self.audioBuffer), "RTP seq:", self.sequence_number, "skipped:",
                             self.packets_skipped)

        except Exception as e:
            logger.error("AudioStreamModule processRemote error:", str(e))
            traceback.print_exc()

    def send_rtp_audio_packet(self, audio_data, send_time):
        """Send RTP audio packet with proper L16 payload"""
        try:
            # Ensure exactly 256 samples
            audio_array = np.array(audio_data, dtype=np.int16)
            if len(audio_array) != CHUNK_SIZE:
                logger.warning("Audio chunk size mismatch: expected %d, got %d",
                    CHUNK_SIZE, len(audio_array))
                # Pad or truncate to exact size
                if len(audio_array) < CHUNK_SIZE:
                    padding = np.zeros(CHUNK_SIZE - len(audio_array), dtype=np.int16)
                    audio_array = np.concatenate([audio_array, padding])
                else:
                    audio_array = audio_array[:CHUNK_SIZE]
            
            # Validate audio data range
            audio_array = np.clip(audio_array, -32768, 32767)
            
            # Create RTP header
            # Note: RTP timestamp represents the sampling instant of the first sample
            rtp_header = self.create_rtp_header(self.sequence_number, self.rtp_timestamp)
            
            # Convert audio to bytes (network byte order - big-endian for L16)
            # L16 payload format uses big-endian 16-bit samples
            audio_bytes = audio_array.astype('>i2').tostring()  # Big-endian int16
            
            # Verify payload size (256 samples * 2 bytes = 512 bytes)
            if len(audio_bytes) != 512:
                logger.error("Audio payload size incorrect: %d bytes (expected 512)", len(audio_bytes))
                return
            
            # Create complete RTP packet
            rtp_packet = rtp_header + audio_bytes
            total_packet_size = RTP_HEADER_SIZE + len(audio_bytes)
            
            # Verify total packet size
            if len(rtp_packet) != total_packet_size:
                logger.error("RTP packet size incorrect: %d bytes (expected %d)",
                    len(rtp_packet), total_packet_size)
                return
            
            # Send RTP packet
            try:
                bytes_sent = self.sock.sendto(rtp_packet, (self.target_host, self.target_port))
                
                if bytes_sent != len(rtp_packet):
                    logger.warning("RTP: WARNING - Partial send: %d of %d bytes",
                        bytes_sent, len(rtp_packet))
                
                # Update RTP session state
                self.last_packet_time = send_time
                self.packets_sent += 1
                self.bytes_sent += bytes_sent
                self.sequence_number = (self.sequence_number + 1) & 0xFFFF  # 16-bit rollover
                self.rtp_timestamp = (self.rtp_timestamp + self.timestamp_increment) & 0xFFFFFFFF  # 32-bit rollover
                
                # Detailed logging every 10 packets
                if self.sequence_number % 10 == 0:
                    rms = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2)) if len(audio_array) > 0 else 0
                    logger.debug("RTP: seq:%d ts:%d -> %s:%d | %dB | RMS:%.0f | time:%.3fs",
                        self.sequence_number, self.rtp_timestamp, self.target_host, self.target_port, 
                        len(rtp_packet), rms, send_time)
                
                # Network stats every 50 packets
                if self.sequence_number % 50 == 0:
                    elapsed = send_time - self.last_network_log_time
                    if elapsed > 0:
                        actual_rate = 50.0 / elapsed
                        expected_rate = 1.0 / PACKET_INTERVAL
                        rate_accuracy = (actual_rate / expected_rate * 100)
                        logger.debug("RTP: Rate %.1f/%.1f pkt/s (%.1f%%) | SSRC:0x%08X | %d errs",
                            actual_rate, expected_rate, rate_accuracy, self.ssrc, self.network_errors)
                    self.last_network_log_time = send_time
                
            except socket.error as e:
                self.network_errors += 1
                logger.error("RTP: Socket error #%d:", self.network_errors, e)
                
                # Recreate socket after multiple errors
                if self.network_errors % 10 == 0:
                    logger.warning("RTP: Recreating socket after %d errors", self.network_errors)
                    try:
                        self.sock.close()
                        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        logger.info("RTP: Socket recreated successfully")
                    except Exception as recreate_error:
                        logger.error("RTP: Failed to recreate socket:", recreate_error)
            
            # Volume display every 50 packets
            if self.sequence_number % 50 == 0:
                rms = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2)) if len(audio_array) > 0 else 0
                volume_bar = '#' * min(20, int(rms // 1000))
                logger.debug("Volume: [%s%s] %.0f RMS (seq: %d)",
                    volume_bar, ' ' * (20 - len(volume_bar)), rms, self.sequence_number)
                
        except Exception as e:
            logger.error("Failed to send RTP audio packet:", str(e))
            traceback.print_exc()

    def set_target(self, host, port):
        """Change target host and port for RTP streaming"""
        self.target_host = host
        self.target_port = port
        logger.info("RTP Audio stream target changed to %s:%s", host, port)

    def get_sequence(self):
        """Get current RTP sequence number"""
        return self.sequence_number

    def get_streaming_status(self):
        """Get current RTP streaming status"""
        return {
            'streaming': self.isStreamingEnabled,
            'started': self.isStarted,
            'rtp_sequence': self.sequence_number,
            'rtp_timestamp': self.rtp_timestamp,
            'rtp_ssrc': self.ssrc,
            'target': "{}:{}".format(self.target_host, self.target_port),
            'buffer_size': len(self.audioBuffer),
            'payload_type': 'L16/{}'.format(SAMPLE_RATE)
        }

    def __del__(self):
        """Enhanced destructor that handles all cleanup gracefully"""
        logger.info("cleaning everything")
        
        try:
            # Disable streaming if active
            if hasattr(self, 'isStreamingEnabled') and self.isStreamingEnabled:
                try:
                    self.disable_stream()
                except:
                    pass
            
            # Stop GStreamer pipeline if exists
            if hasattr(self, 'pipeline') and self.pipeline and hasattr(self, 'gstreamer_available') and self.gstreamer_available:
                try:
                    self.pipeline.set_state(self.gst.STATE_NULL)
                    self.pipeline = None
                except:
                    pass
            
            # Unsubscribe from events if memory is still available
            if hasattr(self, 'memory'):
                try:
                    self.memory.unsubscribe("ControlAudioStreaming", self.getName())
                    self.memory.unsubscribe("Speaking", self.getName())
                except Exception as e:
                    logger.warning("Could not unsubscribe from audio stream events:", e)
                    
        except Exception as e:
            logger.error("Error during AudioStreamModule cleanup:", e)
        finally:
            logger.info("cleaned up!")

    def stop(self):
        """Stop the audio stream module and clean up"""
        try:
            self.disable_stream()
            
            # Unsubscribe from events
            try:
                if hasattr(self, 'memory'):
                    self.memory.unsubscribe("ControlAudioStreaming", self.getName())
                    self.memory.unsubscribe("Speaking", self.getName())
            except Exception as e:
                logger.warning("Could not unsubscribe from audio stream events:", e)
                
        except Exception as e:
            logger.error("Error during AudioStreamModule stop:", e)
        finally:
            logger.info("stopped!")

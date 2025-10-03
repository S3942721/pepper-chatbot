#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Pepper Robot Audio Transmitter
Real-time audio streaming using GStreamer
Python 2.7 compatible
"""

import sys
import time
import socket

# Add GStreamer path
sys.path.append('/usr/lib/python2.7/site-packages/gst-0.10')

try:
    import gst
    import gobject
    gobject.threads_init()
except ImportError as e:
    print("Error importing GStreamer: %s" % e)
    print("Make sure GStreamer Python bindings are installed")
    sys.exit(1)

class AudioStreamer:
    def __init__(self, target_ip, target_port=5004):
        self.target_ip = target_ip
        self.target_port = target_port
        self.pipeline = None
        self.loop = None
        
    def create_pipeline(self):
        """Create GStreamer pipeline for audio streaming"""
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
        ) % (self.target_ip, self.target_port)
        
        print("Creating pipeline: %s" % pipeline_desc)
        
        try:
            self.pipeline = gst.parse_launch(pipeline_desc)
        except Exception as e:
            print("Error creating pipeline: %s" % e)
            return False
            
        # Set up message handling
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_message)
        
        return True
    
    def on_message(self, bus, message):
        """Handle GStreamer messages"""
        if message.type == gst.MESSAGE_ERROR:
            err, debug = message.parse_error()
            print("Error: %s" % err)
            print("Debug: %s" % debug)
            self.stop()
        elif message.type == gst.MESSAGE_EOS:
            print("End of stream")
            self.stop()
        elif message.type == gst.MESSAGE_STATE_CHANGED:
            old_state, new_state, pending_state = message.parse_state_changed()
            if message.src == self.pipeline:
                print("Pipeline state changed from %s to %s" % 
                      (old_state.value_name, new_state.value_name))
    
    def start(self):
        """Start audio streaming"""
        if not self.create_pipeline():
            return False
            
        print("Starting audio stream to %s:%d" % (self.target_ip, self.target_port))
        
        # Start the pipeline
        self.pipeline.set_state(gst.STATE_PLAYING)
        
        # Create main loop
        self.loop = gobject.MainLoop()
        
        try:
            print("Streaming... Press Ctrl+C to stop")
            self.loop.run()
        except KeyboardInterrupt:
            print("\nStopping stream...")
            self.stop()
        
        return True
    
    def stop(self):
        """Stop audio streaming"""
        if self.pipeline:
            self.pipeline.set_state(gst.STATE_NULL)
        if self.loop:
            self.loop.quit()

def test_network_connection(target_ip, target_port):
    """Test if target device is reachable"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1)
        sock.sendto("test", (target_ip, target_port))
        sock.close()
        return True
    except:
        return False

def main():
    if len(sys.argv) != 2:
        print("Usage: %s <target_ip>" % sys.argv[0])
        print("Example: %s 192.168.1.100" % sys.argv[0])
        sys.exit(1)
    
    target_ip = sys.argv[1]
    target_port = 5004
    
    print("Pepper Audio Streamer")
    print("Target: %s:%d" % (target_ip, target_port))
    
    # Test audio devices
    print("Testing audio devices...")
    try:
        test_pipeline = gst.parse_launch("alsasrc device=default ! fakesink")
        test_pipeline.set_state(gst.STATE_PLAYING)
        time.sleep(1)
        test_pipeline.set_state(gst.STATE_NULL)
        print("Audio device OK")
    except Exception as e:
        print("Warning: Audio device test failed: %s" % e)
    
    # Create and start streamer
    streamer = AudioStreamer(target_ip, target_port)
    streamer.start()

if __name__ == "__main__":
    main()

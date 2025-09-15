import socket
import json
import threading
import time
import struct
import numpy as np
import re
from naoqi import ALProxy, ALModule
import logger

class SocketClient(ALModule):
    def __init__(self, name, nao_ip, nao_port, server_addr, server_port):
        ALModule.__init__(self, name)
        self.BIND_PYTHON(self.getName(), "callback")
        
        self.memory = ALProxy("ALMemory")
        # Subscribe to Speaking events for status reporting
        self.memory.subscribeToEvent("Speaking", self.getName(), "on_speaking_event")
        # Subscribe to other state events for comprehensive state tracking
        self.memory.subscribeToEvent("ControlRecording", self.getName(), "on_recording_state_change")
        self.memory.subscribeToEvent("RunningBehaviour", self.getName(), "on_behavior_state_change")
        # Subscribe to robot awareness state changes
        self.memory.subscribeToEvent("RobotAwarenessState", self.getName(), "on_robot_awareness_state_change")
        
        self.server_addr = server_addr
        self.server_port = server_port
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connected = False
        self.running = True
        
        # Thread for socket communication
        self.socket_thread = None
        
        # Robot state tracking for synchronization
        self.robot_name = "Haku"
        self.speaking_state = False
        self.listening_state = False  
        self.current_behavior = "idle"
        self.conversation_session_id = None
        self.was_speaking = False

    def __del__(self):
        """Enhanced destructor that handles all cleanup gracefully"""
        logger.info("cleaning everything")
        
        try:
            # Stop the socket thread
            self.running = False
            
            # Close socket connection
            if hasattr(self, 'client_socket'):
                try:
                    if self.connected:
                        shutdown_msg = 'SHUTDOWN'
                        logger.info("SOCKET SEND (raw):", shutdown_msg)
                        self.client_socket.sendall(shutdown_msg.encode('utf-8'))
                    self.client_socket.close()
                except:
                    pass
            
            # Wait for socket thread to finish
            if hasattr(self, 'socket_thread') and self.socket_thread and self.socket_thread.is_alive():
                try:
                    self.socket_thread.join(timeout=2)
                except:
                    pass
            
            # Unsubscribe from events if memory is still available
            if hasattr(self, 'memory'):
                try:
                    self.memory.unsubscribeToEvent("Speaking", self.getName())
                    self.memory.unsubscribeToEvent("ControlRecording", self.getName())
                    self.memory.unsubscribeToEvent("RunningBehaviour", self.getName())
                    self.memory.unsubscribeToEvent("RobotAwarenessState", self.getName())
                except Exception as e:
                    logger.warning("Could not unsubscribe from socket events:", e)
                    
        except Exception as e:
            logger.error("Error during SocketClient cleanup:", e)
        finally:
            logger.info("cleaned up!")

    def _send_message(self, message):
        """Helper method to send messages with consistent logging"""
        try:
            message_str = json.dumps(message)
            logger.info("SOCKET SEND (JSON):", message_str)
            self.client_socket.send(message_str.encode() + b'\n')
            logger.debug("SOCKET SEND SUCCESS - Message sent successfully")
            return True
        except Exception as e:
            logger.error("SOCKET SEND ERROR - Failed to send message:", e)
            logger.error("SOCKET SEND ERROR - Message content:", message)
            return False

    def on_speaking_event(self, event_name, is_speaking):
        """Handle speaking state changes and report to server"""
        is_speaking = bool(is_speaking)
        
        # Check for state changes that require notification
        if self.was_speaking and not is_speaking:
            # Robot stopped speaking - immediately notify web controller
            logger.info("Robot stopped speaking - sending state update to web controller")
            self.send_state_update()
        elif not self.was_speaking and is_speaking:
            # Robot started speaking
            self.current_behavior = "speaking"
            logger.info("Robot started speaking - updating behavior to speaking")
        
        self.speaking_state = is_speaking
        self.was_speaking = is_speaking
        
        logger.info("Speaking state changed to:", is_speaking)
        
        # Send speaking state to server
        self.send_speaking_state(is_speaking)

    def send_speaking_state(self, speaking):
        """Send speaking state update to server"""
        if not self.connected:
            logger.warning("Not connected to server, cannot send speaking state")
            return
            
        message = {
            "cmd": "speaking-state",
            "type": "speaking-state",
            "robot": "Haku",
            "message": {
                "speaking": speaking
            },
            "timestamp": time.time()
        }
        
        if self._send_message(message):
            logger.info("Sent speaking state to server:", speaking)
        else:
            logger.error("Failed to send speaking state:", speaking)

    def on_recording_state_change(self, event_name, is_recording):
        """Handle recording/listening state changes"""
        self.listening_state = bool(is_recording)
        logger.debug("Listening state changed to:", self.listening_state)

    def on_behavior_state_change(self, event_name, is_running):
        """Handle behavior state changes"""
        if not is_running and self.current_behavior != "idle":
            self.current_behavior = "idle"
            logger.debug("Behavior finished, set to idle")

    def on_robot_awareness_state_change(self, event_name, state_info):
        """Handle robot awareness state changes and relay to web controller"""
        logger.debug("Robot awareness state changed:", state_info)
        
        if not self.connected:
            logger.warning("Not connected to server, cannot send awareness state")
            return
        
        message = {
            "cmd": "robot_awareness_state",
            "type": "system",
            "awake": state_info.get("awake", False),
            "transitioning": state_info.get("transitioning", False),
            "timestamp": state_info.get("timestamp", int(time.time() * 1000)),
            "robot_name": self.robot_name
        }
        
        if self._send_message(message):
            logger.info("Sent robot awareness state to web controller")
        else:
            logger.error("Failed to send robot awareness state")

    def send_state_update(self):
        """Send proactive state update to web controller"""
        if not self.connected:
            logger.warning("Not connected to server, cannot send state update")
            return
            
        message = {
            "cmd": "state_update",
            "type": "system",
            "speaking": self.speaking_state,
            "listening": self.listening_state,
            "current_behavior": self.current_behavior,
            "conversation_session_id": self.conversation_session_id,
            "timestamp": int(time.time() * 1000),
            "robot_name": self.robot_name
        }
        
        if self._send_message(message):
            logger.info("Sent state update to web controller")
        else:
            logger.error("Failed to send state update")

    def handle_health_check(self, json_data):
        """Handle health check request from web controller"""
        logger.info("Received health check from web controller")
        
        response = {
            "type": "health_check_response",
            "action": "pong",
            "timestamp": int(time.time() * 1000),
            "source": "robot",
            "robot": self.robot_name,
            "status": "healthy"
        }
        
        if self._send_message(response):
            logger.info("Sent health check response")
        else:
            logger.error("Failed to send health check response")

    def handle_state_sync(self, json_data):
        """Handle state sync request from web controller"""
        logger.info("Received state sync request from web controller")
        
        response = {
            "type": "state_sync_response",
            "action": "state_update",
            "timestamp": int(time.time() * 1000),
            "source": "robot",
            "robot": self.robot_name,
            "status": {
                "speaking": self.speaking_state,
                "listening": self.listening_state,
                "moving": False,  # Not currently tracked
                "face_detected": False,  # Not currently tracked
                "current_behavior": self.current_behavior,
                "conversation_session_id": self.conversation_session_id,
                "stt_buffer_state": "ready"  # Default value
            }
        }
        
        if self._send_message(response):
            logger.info("Sent state sync response")
        else:
            logger.error("Failed to send state sync response")

    def handle_stop_action_command(self, json_data):
        """Handle $StopAction command from web controller"""
        logger.info("Received $StopAction command from web controller")
        
        try:
            # Execute StopAction event to stop all activities
            self.memory.raiseEvent("StopAction", None)
            
            # Update internal state immediately
            self.speaking_state = False
            self.current_behavior = "idle"
            self.conversation_session_id = None
            
            # Send state update to confirm the stop
            self.send_state_update()
            
            logger.info("$StopAction executed successfully")
            
        except Exception as e:
            logger.error("Error executing $StopAction:", e)

    def handle_robot_wake_command(self, json_data):
        """Handle robot wake command from web controller"""
        logger.info("Received robot wake command from web controller")
        
        try:
            # Execute robot wake event
            self.memory.raiseEvent("ControlRobotWake", True)
            
            # Send response confirming the command was received
            response = {
                "cmd": "robot_wake_response",
                "type": "system",
                "status": "command_received", 
                "timestamp": int(time.time() * 1000),
                "robot_name": self.robot_name
            }
            
            if self._send_message(response):
                logger.info("Robot wake command executed successfully")
            else:
                logger.error("Failed to send robot wake response")
            
        except Exception as e:
            logger.error("Error executing robot wake command:", e)

    def handle_robot_rest_command(self, json_data):
        """Handle robot rest command from web controller"""
        logger.info("Received robot rest command from web controller")
        
        try:
            # Execute robot rest event
            self.memory.raiseEvent("ControlRobotRest", True)
            
            # Send response confirming the command was received
            response = {
                "cmd": "robot_rest_response",
                "type": "system",
                "status": "command_received",
                "timestamp": int(time.time() * 1000),
                "robot_name": self.robot_name
            }
            
            if self._send_message(response):
                logger.info("Robot rest command executed successfully")
            else:
                logger.error("Failed to send robot rest response")
            
        except Exception as e:
            logger.error("Error executing robot rest command:", e)

    def handle_robot_awareness_status_request(self, json_data):
        """Handle robot awareness status request from web controller"""
        logger.info("Received robot awareness status request from web controller")
        
        try:
            # Request current status from awareness module
            self.memory.raiseEvent("GetRobotAwarenessStatus", True)
            
            # Note: The actual status will be sent via RobotAwarenessState event
            # which should be subscribed to by the socket client if needed
            response = {
                "cmd": "robot_awareness_status_response",
                "type": "system",
                "status": "status_requested",
                "timestamp": int(time.time() * 1000),
                "robot_name": self.robot_name
            }
            
            if self._send_message(response):
                logger.info("Robot awareness status request processed")
            else:
                logger.error("Failed to send robot awareness status response")
            
        except Exception as e:
            logger.error("Error handling robot awareness status request:", e)

    def connection(self):
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((self.server_addr, self.server_port))
            self.connected = True
            logger.info("Socket connected to", self.server_addr, self.server_port)

            # Send robot identification
            identification_message = {
                "cmd": "robot-identify",
                "robot": "Haku",
                "timestamp": time.time()
            }
            
            if self._send_message(identification_message):
                logger.info("Sent robot identification successfully")
            else:
                logger.error("Failed to send robot identification")

        except socket.error as e:
            logger.error("Socket error:", e)
            self.client_socket.close()
            self.connected = False

    def start(self):
        """Start the socket client thread"""
        if not self.socket_thread or not self.socket_thread.is_alive():
            self.running = True
            self.socket_thread = threading.Thread(target=self.run)
            self.socket_thread.daemon = True
            self.socket_thread.start()
            logger.info("Socket client started")

    def run(self):
        buffer = ""
        while self.running:
            if not self.connected:
                self.connection()
                if not self.connected:
                    logger.warning("Connection refused, waiting to retry...")
                    time.sleep(5)  # Wait before retrying
                    continue
            try:
                response = self.client_socket.recv(4096)
                if not response:
                    self.connected = False
                    self.client_socket.close()
                    continue
                
                # Log raw received data
                raw_data = response.decode('utf-8')
                logger.debug("SOCKET RECV (raw):", repr(raw_data))
                
                buffer += raw_data
                while True:
                    try:
                        json_data, index = json.JSONDecoder().raw_decode(buffer)
                        buffer = buffer[index:].lstrip()
                        
                        # Log parsed JSON message
                        logger.info("SOCKET RECV (JSON):", json.dumps(json_data))
                        
                        # Process all messages (removed robot filter since web controller messages don't have robot field)
                        self.process_message(json_data)
                    except ValueError:
                        break
            except socket.error as e:
                logger.error("Socket error:", e)
                self.connected = False
                self.client_socket.close()
                # Continue loop to attempt reconnection
            except Exception as e:
                logger.error("Unexpected error in socket run loop:", e)
                break

    def process_special_events(self, message_text):
        """
        Process special event syntax in messages (e.g., $StopAction=None)
        Returns True if special events were processed, False otherwise
        """
        # Pattern to match $EventName=Value syntax
        event_pattern = r'\$([A-Za-z][A-Za-z0-9_]*)\s*=\s*([^$\s]*)'
        
        matches = re.findall(event_pattern, message_text)
        
        if not matches:
            return False
        
        logger.info("Processing special events from message:", message_text)
        
        for event_name, event_value in matches:
            try:
                # Convert event value to appropriate type
                if event_value.lower() == 'none':
                    value = None
                elif event_value.lower() == 'true':
                    value = True
                elif event_value.lower() == 'false':
                    value = False
                elif event_value.isdigit():
                    value = int(event_value)
                elif '.' in event_value and event_value.replace('.', '').isdigit():
                    value = float(event_value)
                else:
                    value = event_value
                
                logger.info("Executing special event:", event_name, "with value:", value)
                self.memory.raiseEvent(event_name, value)
                
            except Exception as e:
                logger.error("Error processing special event", event_name, ":", e)
        
        return True

    def process_message(self, json_data):
        logger.info("PROCESSING MESSAGE:", json_data)
        try:
            # Handle system messages for robot state synchronization
            message_type = json_data.get('type')
            logger.info("Message type:", message_type)
            
            if message_type in ['system', 'health_check', 'state_sync']:
                # Check both 'cmd' and 'action' fields for compatibility
                cmd = json_data.get('cmd') or json_data.get('action')
                logger.info("Processing system command:", cmd)
                
                if cmd in ['health_check', 'ping']:
                    self.handle_health_check(json_data)
                elif cmd in ['state_sync', 'get_state']:
                    self.handle_state_sync(json_data)
                elif cmd == '$StopAction':
                    self.handle_stop_action_command(json_data)
                elif cmd == 'robot_wake':
                    self.handle_robot_wake_command(json_data)
                elif cmd == 'robot_rest':
                    self.handle_robot_rest_command(json_data)
                elif cmd == 'robot_awareness_status':
                    self.handle_robot_awareness_status_request(json_data)
                else:
                    logger.warning("Unknown system command:", cmd)
                return
            
            # Handle control messages
            if json_data.get('type') == 'control':
                cmd = json_data.get('cmd') or json_data.get('action')
                logger.info("Processing control command:", cmd)
                if cmd == '$StopAction':
                    self.handle_stop_action_command(json_data)
                else:
                    logger.warning("Unknown control command:", cmd)
                return
            
            # Handle existing message types
            message_type = json_data.get('type')
            logger.info("Processing message type:", message_type)
            
            if message_type == 'script':
                msg = str(json_data['message'])
                logger.info("Processing script message:", msg)
                if msg:
                    # Check for special events first
                    if not self.process_special_events(msg):
                        # self.memory.raiseEvent('StopAction', None) # TODO: revisit how to cancel existing actions before running a new item
                        logger.info("Raising 'Say' event with message:", msg)
                        self.memory.raiseEvent('Say', msg)
            elif message_type == 'conversation-response':
                msg = str(json_data['message'])
                logger.info("Processing conversation-response message:", msg)
                if msg:
                    logger.info("Raising 'SayChunk' event with message:", msg)
                    self.memory.raiseEvent('SayChunk', msg)
            elif message_type == 'profile':
                logger.info("Processing profile message:", json_data['message'])
                if 'html' in json_data['message']:
                    logger.info("Raising 'LoadHTML' event")
                    self.memory.raiseEvent("LoadHTML","http://10.234.7.62:3000/")
                if 'flags' in json_data['message']:
                    if 'gap_fill' in json_data['message']['flags']:
                        gap_fill_value = bool(json_data['message']['flags']['gap_fill'])
                        logger.info("Raising 'TriggerGapFill' event with value:", gap_fill_value)
                        self.memory.raiseEvent("TriggerGapFill", gap_fill_value)
            elif message_type == 'trigger':
                logger.info("Processing trigger message:", json_data['message'])
                if 'Signal' in json_data['message'] and 'Value' in json_data['message']:
                    signal = str(json_data['message']['Signal'])
                    value = json_data['message']['Value']
                    if signal is not None and value is not None:
                        logger.info("Raising event:", signal, "with value:", value)
                        self.memory.raiseEvent(signal, value)
            elif message_type == 'shortcut':
                if json_data['message']:
                    msg = str(json_data['message'])
                    logger.info("Processing shortcut message:", msg)
                    # Check for special events first
                    if not self.process_special_events(msg):
                        # self.memory.raiseEvent('StopAction', None) # TODO: revisit how to cancel existing actions before running a new item
                        logger.info("Raising 'Say' event with message:", msg)
                        self.memory.raiseEvent('Say', msg)
            elif message_type == 'trigger-all':
                logger.info("Processing trigger-all message:", json_data['message'])
                for item in json_data['message']:
                    if 'Signal' in item and 'Value' in item:
                        signal = str(item['Signal'])
                        value = item['Value']
                        logger.info("Raising event:", signal, "with value:", value)
                        self.memory.raiseEvent(signal, value)
            elif message_type == 'Move':
                if json_data['message']:
                    key_press_data = json_data['message']
                    key_press_data = [str(key_press_data['key']), bool(key_press_data['holding'])]
                    logger.info("Processing Move message with data:", key_press_data)
                    self.memory.raiseEvent('Move', key_press_data)
            elif message_type == 'ConMove':
                if json_data['message']:
                    cont_move_data = json_data['message']
                    logger.info("Processing ConMove message:", cont_move_data)
                    try:
                        x = float(cont_move_data['x'])
                        y = float(cont_move_data['y'])
                        hx = float(cont_move_data['hx'])
                        hy = float(cont_move_data['hy'])
                        cont_move_data = [x, y, hx, hy]
                        logger.info("Raising 'ContinuousMove' event with data:", cont_move_data)
                        self.memory.raiseEvent('ContinuousMove', cont_move_data)
                    except (ValueError, TypeError) as e:
                        logger.error("Error converting ConMove values to float:", e)
            elif message_type == 'announcement':
                if json_data['message']:
                    greeting_key = str(json_data['message'])
                    logger.info("Processing announcement message:", greeting_key)
                    logger.info("Raising 'ChangeGreetingKey' event with value:", greeting_key)
                    self.memory.raiseEvent('ChangeGreetingKey', greeting_key)
            else:
                logger.warning("Unknown message type:", message_type)
                
        except Exception as e:
            logger.error("Processing message error", e)
            logger.error("Failed message content:", json_data)

    def stop(self):
        """Stop the socket client and clean up resources"""
        try:
            self.running = False
            
            # Close socket connection
            if hasattr(self, 'client_socket'):
                try:
                    if self.connected:
                        shutdown_msg = 'SHUTDOWN'
                        logger.info("SOCKET SEND (raw):", shutdown_msg)
                        self.client_socket.sendall(shutdown_msg.encode('utf-8'))
                    self.client_socket.close()
                    self.connected = False
                except:
                    pass
            
            # Wait for socket thread to finish
            if hasattr(self, 'socket_thread') and self.socket_thread and self.socket_thread.is_alive():
                try:
                    self.socket_thread.join(timeout=2)
                except:
                    pass
            
            # Unsubscribe from events
            try:
                if hasattr(self, 'memory'):
                    self.memory.unsubscribeToEvent("Speaking", self.getName())
                    self.memory.unsubscribeToEvent("ControlRecording", self.getName())
                    self.memory.unsubscribeToEvent("RunningBehaviour", self.getName())
                    self.memory.unsubscribeToEvent("RobotAwarenessState", self.getName())
            except Exception as e:
                logger.warning("Could not unsubscribe from socket events:", e)
                
        except Exception as e:
            logger.error("Error during SocketClient stop:", e)
        finally:
            logger.info("stopped!")

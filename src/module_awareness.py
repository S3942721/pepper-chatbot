# -*- coding: utf-8 -*-
from naoqi import ALProxy, ALModule
import threading
import time
import logger

class AwarenessModule(ALModule):
    """
    Module to manage robot wake/rest state with socket integration
    Handles transitions between awake and resting states
    """
    
    def __init__(self, name, nao_ip, nao_port, wake_on_start=True, rest_on_exit=False):
        ALModule.__init__(self, name)
        self.BIND_PYTHON(self.getName(), "callback")
        
        self.nao_ip = nao_ip
        self.nao_port = nao_port
        self.wake_on_start = wake_on_start
        self.rest_on_exit = rest_on_exit
        
        # State tracking
        self.is_awake = False
        self.transitioning = False
        self.state_lock = threading.Lock()
        
        # Initialize proxies
        try:
            self.motion = ALProxy("ALMotion", self.nao_ip, self.nao_port)
            self.posture = ALProxy("ALRobotPosture", self.nao_ip, self.nao_port)
            self.memory = ALProxy("ALMemory", self.nao_ip, self.nao_port)
            logger.info("Robot awareness module initialized successfully")
        except Exception as e:
            logger.error("Failed to initialize robot awareness module:", e)
            raise
        
        # Subscribe to motion events
        self.memory.subscribeToEvent("robotIsWakeUp", self.getName(), "on_robot_wake_state_change")
        self.memory.subscribeToEvent("ALMotion/Stiffness/wakeUpStarted", self.getName(), "on_wake_started")
        self.memory.subscribeToEvent("ALMotion/Stiffness/wakeUpFinished", self.getName(), "on_wake_finished")
        self.memory.subscribeToEvent("ALMotion/Stiffness/restStarted", self.getName(), "on_rest_started")
        self.memory.subscribeToEvent("ALMotion/Stiffness/restFinished", self.getName(), "on_rest_finished")
        
        # Subscribe to socket control events
        self.memory.subscribeToEvent("ControlRobotWake", self.getName(), "on_control_wake")
        self.memory.subscribeToEvent("ControlRobotRest", self.getName(), "on_control_rest")
        self.memory.subscribeToEvent("GetRobotAwarenessStatus", self.getName(), "on_get_status")
        
        # Subscribe to system events
        self.memory.subscribeToEvent("StopAction", self.getName(), "on_stop_action")
        
        # Initialize robot state
        self._initialize_robot_state()
        
        logger.info("Robot awareness module ready - wake_on_start:", wake_on_start, "rest_on_exit:", rest_on_exit)

    def __del__(self):
        """Enhanced destructor that handles all cleanup gracefully"""
        logger.info("cleaning everything")
        
        try:
            # Handle rest on exit if configured
            if hasattr(self, 'rest_on_exit') and self.rest_on_exit and hasattr(self, 'is_awake') and self.is_awake:
                logger.info("Rest on exit enabled - putting robot to rest")
                try:
                    if hasattr(self, 'motion'):
                        self.motion.rest()
                        time.sleep(2)  # Give time for rest to complete
                except Exception as e:
                    logger.warning("Error during rest on exit:", e)
            
            # Unsubscribe from events if memory is still available
            if hasattr(self, 'memory'):
                try:
                    self.memory.unsubscribeToEvent("robotIsWakeUp", self.getName())
                    self.memory.unsubscribeToEvent("ALMotion/Stiffness/wakeUpStarted", self.getName())
                    self.memory.unsubscribeToEvent("ALMotion/Stiffness/wakeUpFinished", self.getName())
                    self.memory.unsubscribeToEvent("ALMotion/Stiffness/restStarted", self.getName())
                    self.memory.unsubscribeToEvent("ALMotion/Stiffness/restFinished", self.getName())
                    self.memory.unsubscribeToEvent("ControlRobotWake", self.getName())
                    self.memory.unsubscribeToEvent("ControlRobotRest", self.getName())
                    self.memory.unsubscribeToEvent("GetRobotAwarenessStatus", self.getName())
                    self.memory.unsubscribeToEvent("StopAction", self.getName())
                except Exception as e:
                    logger.warning("Could not unsubscribe from awareness events:", e)
                    
        except Exception as e:
            logger.error("Error during AwarenessModule cleanup:", e)
        finally:
            logger.info("cleaned up!")

    def _initialize_robot_state(self):
        """Initialize robot state based on configuration and current status"""
        try:
            # Check current robot wake status
            current_awake = self.motion.robotIsWakeUp()
            logger.info("Current robot wake status:", current_awake)
            
            with self.state_lock:
                self.is_awake = current_awake
            
            # Apply wake_on_start configuration
            if self.wake_on_start and not current_awake:
                logger.info("Wake on start enabled - waking robot")
                self.wake_robot()
            elif not self.wake_on_start and current_awake:
                logger.info("Wake on start disabled - current state is awake, leaving as-is")
            
            # Broadcast initial state
            self._broadcast_state()
            
        except Exception as e:
            logger.error("Error initializing robot state:", e)

    def wake_robot(self):
        """Wake up the robot"""
        with self.state_lock:
            if self.transitioning:
                logger.warning("Robot is already transitioning, ignoring wake request")
                return False
            
            if self.is_awake:
                logger.info("Robot is already awake")
                return True
            
            self.transitioning = True
        
        try:
            logger.info("Waking robot...")
            self.motion.wakeUp()
            
            # Wait for wake up to complete (with timeout)
            timeout = 10.0  # seconds
            start_time = time.time()
            while time.time() - start_time < timeout:
                if self.motion.robotIsWakeUp():
                    break
                time.sleep(0.1)
            
            # Update state
            with self.state_lock:
                self.is_awake = self.motion.robotIsWakeUp()
                self.transitioning = False
            
            if self.is_awake:
                logger.info("Robot wake up completed successfully")
                self._broadcast_state()
                return True
            else:
                logger.warning("Robot wake up may not have completed within timeout")
                return False
                
        except Exception as e:
            logger.error("Error waking robot:", e)
            with self.state_lock:
                self.transitioning = False
            return False

    def rest_robot(self):
        """Put the robot to rest"""
        with self.state_lock:
            if self.transitioning:
                logger.warning("Robot is already transitioning, ignoring rest request")
                return False
            
            if not self.is_awake:
                logger.info("Robot is already at rest")
                return True
            
            self.transitioning = True
        
        try:
            logger.info("Putting robot to rest...")
            
            # Optional: Go to a safe posture before resting
            # This is safer than directly calling rest()
            try:
                self.posture.goToPosture("Crouch", 0.5)
                time.sleep(1)  # Give time for posture change
            except Exception as e:
                logger.warning("Could not go to crouch posture before rest:", e)
            
            self.motion.rest()
            
            # Wait for rest to complete (with timeout)
            timeout = 10.0  # seconds
            start_time = time.time()
            while time.time() - start_time < timeout:
                if not self.motion.robotIsWakeUp():
                    break
                time.sleep(0.1)
            
            # Update state
            with self.state_lock:
                self.is_awake = self.motion.robotIsWakeUp()
                self.transitioning = False
            
            if not self.is_awake:
                logger.info("Robot rest completed successfully")
                self._broadcast_state()
                return True
            else:
                logger.warning("Robot rest may not have completed within timeout")
                return False
                
        except Exception as e:
            logger.error("Error putting robot to rest:", e)
            with self.state_lock:
                self.transitioning = False
            return False

    def _broadcast_state(self):
        """Broadcast current robot awareness state to other modules"""
        try:
            state_info = {
                "awake": self.is_awake,
                "transitioning": self.transitioning,
                "timestamp": int(time.time() * 1000)
            }
            
            self.memory.raiseEvent("RobotAwarenessState", state_info)
            logger.debug("Broadcasted robot awareness state:", state_info)
            
        except Exception as e:
            logger.error("Error broadcasting robot state:", e)

    # Event handlers for motion events
    def on_robot_wake_state_change(self, event_name, is_awake):
        """Handle robotIsWakeUp event"""
        logger.info("Robot wake state changed:", is_awake)
        with self.state_lock:
            self.is_awake = bool(is_awake)
        self._broadcast_state()

    def on_wake_started(self, event_name, value):
        """Handle wake up started event"""
        logger.info("Robot wake up started")
        with self.state_lock:
            self.transitioning = True
        self._broadcast_state()

    def on_wake_finished(self, event_name, value):
        """Handle wake up finished event"""
        logger.info("Robot wake up finished")
        with self.state_lock:
            self.is_awake = True
            self.transitioning = False
        self._broadcast_state()

    def on_rest_started(self, event_name, value):
        """Handle rest started event"""
        logger.info("Robot rest started")
        with self.state_lock:
            self.transitioning = True
        self._broadcast_state()

    def on_rest_finished(self, event_name, value):
        """Handle rest finished event"""
        logger.info("Robot rest finished")
        with self.state_lock:
            self.is_awake = False
            self.transitioning = False
        self._broadcast_state()

    # Event handlers for socket control
    def on_control_wake(self, event_name, value):
        """Handle wake control from socket"""
        logger.info("Received wake control command from socket")
        wake_thread = threading.Thread(target=self.wake_robot)
        wake_thread.daemon = True
        wake_thread.start()

    def on_control_rest(self, event_name, value):
        """Handle rest control from socket"""
        logger.info("Received rest control command from socket")
        rest_thread = threading.Thread(target=self.rest_robot)
        rest_thread.daemon = True
        rest_thread.start()

    def on_get_status(self, event_name, value):
        """Handle status request from socket"""
        logger.debug("Received status request from socket")
        self._broadcast_state()

    def on_stop_action(self, event_name, value):
        """Handle StopAction event - ensure robot stays awake for safety"""
        logger.info("StopAction received - ensuring robot stays awake for safety")
        # if not self.is_awake and not self.transitioning:
        #     logger.info("Robot was at rest during StopAction - waking for safety")
        #     wake_thread = threading.Thread(target=self.wake_robot)
        #     wake_thread.daemon = True
        #     wake_thread.start()

    # Public API methods
    def get_status(self):
        """Get current robot awareness status"""
        with self.state_lock:
            return {
                "awake": self.is_awake,
                "transitioning": self.transitioning,
                "wake_on_start": self.wake_on_start,
                "rest_on_exit": self.rest_on_exit
            }

    def force_wake(self):
        """Force wake robot (synchronous)"""
        return self.wake_robot()

    def force_rest(self):
        """Force rest robot (synchronous)"""
        return self.rest_robot()

    def set_stiffness(self, joint_names, stiffness_values):
        """Set joint stiffness (advanced control)"""
        try:
            self.motion.setStiffnesses(joint_names, stiffness_values)
            logger.info("Set stiffness for", joint_names, "to", stiffness_values)
            return True
        except Exception as e:
            logger.error("Error setting stiffness:", e)
            return False

    def get_stiffness(self, joint_names):
        """Get joint stiffness values"""
        try:
            stiffness = self.motion.getStiffnesses(joint_names)
            logger.debug("Stiffness for", joint_names, ":", stiffness)
            return stiffness
        except Exception as e:
            logger.error("Error getting stiffness:", e)
            return None

    def stop(self):
        """Stop the awareness module and clean up"""
        try:
            # Handle rest on exit if configured
            if self.rest_on_exit and self.is_awake:
                logger.info("Rest on exit enabled - putting robot to rest")
                self.rest_robot()
            
            # Unsubscribe from events
            if hasattr(self, 'memory'):
                try:
                    self.memory.unsubscribeToEvent("robotIsWakeUp", self.getName())
                    self.memory.unsubscribeToEvent("ALMotion/Stiffness/wakeUpStarted", self.getName())
                    self.memory.unsubscribeToEvent("ALMotion/Stiffness/wakeUpFinished", self.getName())
                    self.memory.unsubscribeToEvent("ALMotion/Stiffness/restStarted", self.getName())
                    self.memory.unsubscribeToEvent("ALMotion/Stiffness/restFinished", self.getName())
                    self.memory.unsubscribeToEvent("ControlRobotWake", self.getName())
                    self.memory.unsubscribeToEvent("ControlRobotRest", self.getName())
                    self.memory.unsubscribeToEvent("GetRobotAwarenessStatus", self.getName())
                    self.memory.unsubscribeToEvent("StopAction", self.getName())
                except Exception as e:
                    logger.warning("Could not unsubscribe from events:", e)
                    
        except Exception as e:
            logger.error("Error during AwarenessModule stop:", e)
        finally:
            logger.info("stopped!")
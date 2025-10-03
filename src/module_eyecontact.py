import threading
from naoqi import ALProxy, ALModule
import logger

class EyeContactModule(ALModule):
    def __init__(self, name):
        ALModule.__init__(self, name)
        self.BIND_PYTHON(self.getName(), "callback")

        self.face_detected = False
        self.memory = ALProxy("ALMemory")
        self.memory.subscribeToEvent("FaceDetected", name, "on_face_detected")
        self.memory.subscribeToEvent("RunningBehaviour", name, "on_face_detected")
        self.face_lost_timer = None
        self.face_lost_timeout = 30

    def __del__(self):
        """Enhanced destructor that handles all cleanup gracefully"""
        logger.info("cleaning everything")
        
        try:
            # Cancel any active timers
            if hasattr(self, 'face_lost_timer') and self.face_lost_timer:
                try:
                    self.face_lost_timer.cancel()
                    self.face_lost_timer = None
                except:
                    pass
            
            # Unsubscribe from events if memory is still available
            if hasattr(self, 'memory'):
                try:
                    self.memory.unsubscribeToEvent("FaceDetected", self.getName())
                    self.memory.unsubscribeToEvent("RunningBehaviour", self.getName())
                except Exception as e:
                    logger.warning("Could not unsubscribe from eye contact events:", e)
                    
        except Exception as e:
            logger.error("Error during EyeContactModule cleanup:", e)
        finally:
            logger.info("cleaned up!")

    def on_face_detected(self, event_name, value):
        if value:
            if not self.face_detected:
                # logger.info("Face detected")
                self.handle_status_change(True)
            if self.face_lost_timer:
                self.face_lost_timer.cancel()
                self.face_lost_timer = None
        else:
            if self.face_detected:
                # logger.info("Face lost")
                self.face_lost_timer = threading.Timer(self.face_lost_timeout, self.handle_status_change, [False])
                self.face_lost_timer.start()

    def handle_status_change(self, status):
        self.face_detected = status
        # logger.info("Eye contact is %s", "ON" if status else "OFF")
        self.memory.raiseEvent('EyeContact', status)
        if not self.face_detected:
            # logger.info("Resetting conversation")
            self.memory.raiseEvent('ResetConversation', True)

    def stop(self):
        self.memory.unsubscribeToEvent("FaceDetected", self.getName())
        if self.face_lost_timer:
            self.face_lost_timer.cancel()
        logger.info("stopped!")
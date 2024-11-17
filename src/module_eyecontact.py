import threading
from naoqi import ALProxy, ALModule

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
        print("INF: EyeContactModule.__del__: cleaning everything")
        self.stop()

    def on_face_detected(self, event_name, value):
        if value:
            if not self.face_detected:
                # print("Face detected")
                self.handle_status_change(True)
            if self.face_lost_timer:
                self.face_lost_timer.cancel()
                self.face_lost_timer = None
        else:
            if self.face_detected:
                self.face_lost_timer = threading.Timer(self.face_lost_timeout, self.handle_status_change, [False])
                self.face_lost_timer.start()

    def handle_status_change(self, status):
        self.face_detected = status
        print("INF: EyeContactModule: Eye contact is", "ON" if status else "OFF")
        self.memory.raiseEvent('EyeContact', status)
        if not self.face_detected:
            print("INF: EyeContactModule: Resetting conversation")
            self.memory.raiseEvent('ResetConversation', True)

    def stop(self):
        self.memory.unsubscribeToEvent("FaceDetected", self.getName())
        if self.face_lost_timer:
            self.face_lost_timer.cancel()
        print("INF: EyeContactModule: stopped!")
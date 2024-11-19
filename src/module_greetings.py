import threading
import time
import random
from naoqi import ALProxy, ALModule

class GreetingsModule(ALModule):
    def __init__(self, name):
        ALModule.__init__(self, name)
        self.BIND_PYTHON(self.getName(), "callback")

        self.face_detected = False
        self.memory = ALProxy("ALMemory")
        self.memory.subscribeToEvent("FaceDetected", name, "on_face_detected")
        self.memory.subscribeToEvent("ControlGreetings", name, "on_control_greetings")
        self.memory.subscribeToEvent("GreetingsRequireFaceLost", name, "on_greetings_require_face_lost")
        self.SPEAK_TIMEOUT = 8 # seconds to wait before speaking again
        self.FACE_LOST_TIMEOUT = 1 # seconds until face is considered lost
        self.enabled_greetings = True
        self.last_spoken_time = 0
        self.has_been_greeted = False
        self.require_face_lost = False
        self.face_lost_timer = None
        self.RESPONSE_SPEED = 90
        self.RESPONSE_STRING = "\\\\rspd=" + str(self.RESPONSE_SPEED) + "\\\\"
        
        self.GREETINGS = [
                    "^start(hey) {0} Hello ^wait(hey)".format(self.RESPONSE_STRING), 
                    "^start(hey) {0} Howdy ^wait(hey)".format(self.RESPONSE_STRING), 
                    "^start(hey) {0} Hi ^wait(hey)".format(self.RESPONSE_STRING), 
                    "^start(hey) {0} Hey ^wait(hey)".format(self.RESPONSE_STRING), 
                    "^start(hey) {0} Glad you came ^wait(hey)".format(self.RESPONSE_STRING), 
                    "^start(hey) {0} Welcome ^wait(hey)".format(self.RESPONSE_STRING), 
                    "^start(hey) {0} Welcome in ^wait(hey)".format(self.RESPONSE_STRING), 
                    "^start(hey) {0} Nice to see you here ^wait(hey)".format(self.RESPONSE_STRING), 
                    "^start(hey) {0} Greetings, I'm Pepper ^wait(hey)".format(self.RESPONSE_STRING),
                    "^start(hey) {0} Hello, I'm Pepper ^wait(hey)".format(self.RESPONSE_STRING),
                    "^start(hey) {0} Welcome, I'm Pepper ^wait(hey)".format(self.RESPONSE_STRING),
                    "^start(hey) {0} Hey, my name is Pepper ^wait(hey)".format(self.RESPONSE_STRING),
                    "^start(bowshort) {0} Welcome ^wait(bowshort)".format(self.RESPONSE_STRING), 
                    "^start(bowshort) {0} Welcome in ^wait(bowshort)".format(self.RESPONSE_STRING), 
                    "^start(bowshort) {0} Nice to see you here ^wait(bowshort)".format(self.RESPONSE_STRING), 
                    "^start(bowshort) {0} Greetings, I'm Pepper ^wait(bowshort)".format(self.RESPONSE_STRING),
                    "^start(bowshort) {0} Hello, I'm Pepper ^wait(bowshort)".format(self.RESPONSE_STRING),
                    "^start(bowshort) {0} Welcome, I'm Pepper ^wait(bowshort)".format(self.RESPONSE_STRING),
                    "^start(bowshort) {0} Hello, my name is Pepper ^wait(bowshort)".format(self.RESPONSE_STRING),
                    "^start(salute) {0} Welcome ^wait(salute)".format(self.RESPONSE_STRING), 
                    "^start(salute) {0} Welcome in ^wait(salute)".format(self.RESPONSE_STRING), 
                    "^start(salute) {0} Nice to see you here ^wait(salute)".format(self.RESPONSE_STRING), 
                    "^start(salute) {0} Greetings, I'm Pepper ^wait(salute)".format(self.RESPONSE_STRING),
                    "^start(salute) {0} Hello, I'm Pepper ^wait(salute)".format(self.RESPONSE_STRING),
                    "^start(salute) {0} Welcome, I'm Pepper ^wait(salute)".format(self.RESPONSE_STRING),
                    "^start(salute) {0} Welcome, my name is Pepper ^wait(salute)".format(self.RESPONSE_STRING),
        ]

    def __del__(self):
        print("INF: GreetingsModule.__del__: cleaning everything")
        self.stop()
        
    def on_control_greetings(self, event_name, value):
        self.enabled_greetings = value
        print("INF: GreetingsModule: Greetings are", "ON" if value else "OFF")

    def on_greetings_require_face_lost(self, event_name, value):
        self.require_face_lost = value
        print("INF: GreetingsModule: Greetings require face lost is", "ON" if value else "OFF")

    def on_face_detected(self, event_name, value):
        if not self.enabled_greetings:
            return
        if value:
            if not self.face_detected:
                print("Face detected")
                self.handle_status_change(True)
                self.say_greeting()
            if self.face_lost_timer:
                self.face_lost_timer.cancel()
                self.face_lost_timer = None
        else:
            print("Face lost")
            if self.face_detected:
                self.face_lost_timer = threading.Timer(self.FACE_LOST_TIMEOUT, self.handle_status_change, [False])
                self.face_lost_timer.start()

    def handle_status_change(self, status):
        if not self.enabled_greetings:
            return
        self.face_detected = status
        if not status:
            self.has_been_greeted = False

    def say_greeting(self):
        if not self.enabled_greetings:
            return
        print("INF: GreetingsModule: Saying greeting")
        current_time = time.time()
        if current_time - self.last_spoken_time > self.SPEAK_TIMEOUT and not (self.require_face_lost and self.has_been_greeted):
            self.has_been_greeted = True
            greeting = random.choice(self.GREETINGS)
            self.memory.raiseEvent('Say', greeting)
            self.last_spoken_time = current_time

    def stop(self):
        self.memory.unsubscribeToEvent("FaceDetected", self.getName())
        self.memory.unsubscribeToEvent("ControlGreetings", self.getName())
        self.memory.unsubscribeToEvent("GreetingsRequireFaceLost", self.getName())
        if self.face_lost_timer:
            self.face_lost_timer.cancel()
        print("INF: GreetingsModule: stopped!")
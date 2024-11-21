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
        self.memory.subscribeToEvent("LoadHTML", name, "update_profile")
        self.memory.subscribeToEvent("ChangeGreetTimeout", name, "on_speak_timeout_change")
        self.memory.subscribeToEvent("ChangeGreetFaceLostTimeout", name, "on_face_lost_timeout_change")

        self.DEFAULT_SPEAK_TIMEOUT = 3 # default seconds to wait before speaking again
        self.speak_timeout = self.DEFAULT_SPEAK_TIMEOUT # seconds to wait before speaking again
        self.DEFAULT_FACE_LOST_TIMEOUT = 1 # default seconds until face is considered lost
        self.face_lost_timeout = self.DEFAULT_FACE_LOST_TIMEOUT # seconds until face is considered lost
        self.enabled_greetings = False
        self.last_spoken_time = 0
        self.has_been_greeted = False
        self.require_face_lost = False
        self.face_lost_timer = None
        self.response_speed = 90
        self.response_string = "\\\\rspd=" + str(self.response_speed) + "\\\\"
        self.waiting_for_greeting = False
        
        self.CN_GREETINGS = [
            "^start(hey) {0} Hello ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Howdy ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Hi ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Hey ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Glad you came ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Welcome ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Welcome in ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Nice to see you here ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Greetings, I'm Pepper ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Hello, I'm Pepper ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Welcome, I'm Pepper ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Hey, my name is Pepper ^wait(hey)".format(self.response_string),
            "^start(bowshort) {0} Welcome ^wait(bowshort)".format(self.response_string), 
            "^start(bowshort) {0} Welcome in ^wait(bowshort)".format(self.response_string), 
            "^start(bowshort) {0} Nice to see you here ^wait(bowshort)".format(self.response_string), 
            "^start(bowshort) {0} Greetings, I'm Pepper ^wait(bowshort)".format(self.response_string),
            "^start(bowshort) {0} Hello, I'm Pepper ^wait(bowshort)".format(self.response_string),
            "^start(bowshort) {0} Welcome, I'm Pepper ^wait(bowshort)".format(self.response_string),
            "^start(bowshort) {0} Hello, my name is Pepper ^wait(bowshort)".format(self.response_string),
            "^start(salute) {0} Welcome ^wait(salute)".format(self.response_string), 
            "^start(salute) {0} Welcome in ^wait(salute)".format(self.response_string), 
            "^start(salute) {0} Nice to see you here ^wait(salute)".format(self.response_string), 
            "^start(salute) {0} Greetings, I'm Pepper ^wait(salute)".format(self.response_string),
            "^start(salute) {0} Hello, I'm Pepper ^wait(salute)".format(self.response_string),
            "^start(salute) {0} Welcome, I'm Pepper ^wait(salute)".format(self.response_string),
            "^start(salute) {0} Welcome, my name is Pepper ^wait(salute)".format(self.response_string),
            "^start(hey) {0} Hello, welcome to RMIT's City North end of year showcase ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Howdy, welcome to RMIT's City North end of year showcase ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Hi, welcome to RMIT's City North end of year showcase ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Hey, welcome to RMIT's City North end of year showcase ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Glad you came to RMIT's City North end of year showcase ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Welcome to RMIT's City North end of year showcase ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Welcome in to RMIT's City North end of year showcase ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Nice to see you here at RMIT's City North end of year showcase ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Greetings, I'm Pepper, welcome to RMIT's City North end of year showcase ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Hello, I'm Pepper, welcome to RMIT's City North end of year showcase ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Welcome, I'm Pepper, welcome to RMIT's City North end of year showcase ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Hey, my name is Pepper, welcome to RMIT's City North end of year showcase ^wait(hey)".format(self.response_string),
            "^start(bowshort) {0} Welcome to RMIT's City North end of year showcase ^wait(bowshort)".format(self.response_string), 
            "^start(bowshort) {0} Welcome in to RMIT's City North end of year showcase ^wait(bowshort)".format(self.response_string), 
            "^start(bowshort) {0} Nice to see you here at RMIT's City North end of year showcase ^wait(bowshort)".format(self.response_string), 
            "^start(bowshort) {0} Greetings, I'm Pepper, welcome to RMIT's City North end of year showcase ^wait(bowshort)".format(self.response_string),
            "^start(bowshort) {0} Hello, I'm Pepper, welcome to RMIT's City North end of year showcase ^wait(bowshort)".format(self.response_string),
            "^start(bowshort) {0} Welcome, I'm Pepper, welcome to RMIT's City North end of year showcase ^wait(bowshort)".format(self.response_string),
            "^start(bowshort) {0} Hello, my name is Pepper, welcome to RMIT's City North end of year showcase ^wait(bowshort)".format(self.response_string),
            "^start(salute) {0} Welcome to RMIT's City North end of year showcase ^wait(salute)".format(self.response_string), 
            "^start(salute) {0} Welcome in to RMIT's City North end of year showcase ^wait(salute)".format(self.response_string), 
            "^start(salute) {0} Nice to see you here at RMIT's City North end of year showcase ^wait(salute)".format(self.response_string), 
            "^start(salute) {0} Greetings, I'm Pepper, welcome to RMIT's City North end of year showcase ^wait(salute)".format(self.response_string),
            "^start(salute) {0} Hello, I'm Pepper, welcome to RMIT's City North end of year showcase ^wait(salute)".format(self.response_string),
            "^start(salute) {0} Welcome, I'm Pepper, welcome to RMIT's City North end of year showcase ^wait(salute)".format(self.response_string),
            "^start(salute) {0} Welcome, my name is Pepper, welcome to RMIT's City North end of year showcase ^wait(salute)".format(self.response_string),
            "^start(hey) {0} Welcome to the showcase ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Hi, welcome to the showcase ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Hey, welcome to the showcase ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Glad you came to the showcase ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Nice to see you here at the showcase ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Hello, I'm Pepper, welcome to the showcase ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Welcome, I'm Pepper, welcome to the showcase ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Hey, my name is Pepper, welcome to the showcase ^wait(hey)".format(self.response_string),
        ]

        self.LTQ_GREETINGS = [
            "^start(hey) {0} Hello ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Howdy ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Hi ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Hey ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Glad you came ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Welcome ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Welcome in ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Nice to see you here ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Greetings, I'm Pepper ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Hello, I'm Pepper ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Welcome, I'm Pepper ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Hey, my name is Pepper ^wait(hey)".format(self.response_string),
            "^start(bowshort) {0} Welcome ^wait(bowshort)".format(self.response_string), 
            "^start(bowshort) {0} Welcome in ^wait(bowshort)".format(self.response_string), 
            "^start(bowshort) {0} Nice to see you here ^wait(bowshort)".format(self.response_string), 
            "^start(bowshort) {0} Greetings, I'm Pepper ^wait(bowshort)".format(self.response_string),
            "^start(bowshort) {0} Hello, I'm Pepper ^wait(bowshort)".format(self.response_string),
            "^start(bowshort) {0} Welcome, I'm Pepper ^wait(bowshort)".format(self.response_string),
            "^start(bowshort) {0} Hello, my name is Pepper ^wait(bowshort)".format(self.response_string),
            "^start(salute) {0} Welcome ^wait(salute)".format(self.response_string), 
            "^start(salute) {0} Welcome in ^wait(salute)".format(self.response_string), 
            "^start(salute) {0} Nice to see you here ^wait(salute)".format(self.response_string), 
            "^start(salute) {0} Greetings, I'm Pepper ^wait(salute)".format(self.response_string),
            "^start(salute) {0} Hello, I'm Pepper ^wait(salute)".format(self.response_string),
            "^start(salute) {0} Welcome, I'm Pepper ^wait(salute)".format(self.response_string),
            "^start(salute) {0} Welcome, my name is Pepper ^wait(salute)".format(self.response_string),
            "^start(hey) {0} Hello, welcome to the STEM Learning and Teaching Showcase ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Howdy, welcome to the STEM Learning and Teaching Showcase ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Hi, welcome to the STEM Learning and Teaching Showcase ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Hey, welcome to the STEM Learning and Teaching Showcase ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Glad you came to the STEM Learning and Teaching Showcase ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Welcome to the STEM Learning and Teaching Showcase ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Welcome in to the STEM Learning and Teaching Showcase ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Nice to see you here at the STEM Learning and Teaching Showcase ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Greetings, I'm Pepper, welcome to the STEM Learning and Teaching Showcase ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Hello, I'm Pepper, welcome to the STEM Learning and Teaching Showcase ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Welcome, I'm Pepper, welcome to the STEM Learning and Teaching Showcase ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Hey, my name is Pepper, welcome to the STEM Learning and Teaching Showcase ^wait(hey)".format(self.response_string),
            "^start(bowshort) {0} Welcome to the STEM Learning and Teaching Showcase ^wait(bowshort)".format(self.response_string), 
            "^start(bowshort) {0} Welcome in to the STEM Learning and Teaching Showcase ^wait(bowshort)".format(self.response_string), 
            "^start(bowshort) {0} Nice to see you here at the STEM Learning and Teaching Showcase ^wait(bowshort)".format(self.response_string), 
            "^start(bowshort) {0} Greetings, I'm Pepper, welcome to the STEM Learning and Teaching Showcase ^wait(bowshort)".format(self.response_string),
            "^start(bowshort) {0} Hello, I'm Pepper, welcome to the STEM Learning and Teaching Showcase ^wait(bowshort)".format(self.response_string),
            "^start(bowshort) {0} Welcome, I'm Pepper, welcome to the STEM Learning and Teaching Showcase ^wait(bowshort)".format(self.response_string),
            "^start(bowshort) {0} Hello, my name is Pepper, welcome to the STEM Learning and Teaching Showcase ^wait(bowshort)".format(self.response_string),
            "^start(salute) {0} Welcome to the STEM Learning and Teaching Showcase ^wait(salute)".format(self.response_string), 
            "^start(salute) {0} Welcome in to the STEM Learning and Teaching Showcase ^wait(salute)".format(self.response_string), 
            "^start(salute) {0} Nice to see you here at the STEM Learning and Teaching Showcase ^wait(salute)".format(self.response_string), 
            "^start(salute) {0} Greetings, I'm Pepper, welcome to the STEM Learning and Teaching Showcase ^wait(salute)".format(self.response_string),
            "^start(salute) {0} Hello, I'm Pepper, welcome to the STEM Learning and Teaching Showcase ^wait(salute)".format(self.response_string),
            "^start(salute) {0} Welcome, I'm Pepper, welcome to the STEM Learning and Teaching Showcase ^wait(salute)".format(self.response_string),
            "^start(salute) {0} Welcome, my name is Pepper, welcome to the STEM Learning and Teaching Showcase ^wait(salute)".format(self.response_string),
            "^start(hey) {0} Welcome to the showcase ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Hi, welcome to the showcase ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Hey, welcome to the showcase ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Glad you came to the showcase ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Nice to see you here at the showcase ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Hello, I'm Pepper, welcome to the showcase ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Welcome, I'm Pepper, welcome to the showcase ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Hey, my name is Pepper, welcome to the showcase ^wait(hey)".format(self.response_string),
            "^start(hey) {0} I hope you enjoy the showcase ^wait(hey)".format(self.response_string),
            "^start(bowshort) {0} I hope you enjoy the showcase ^wait(bowshort)".format(self.response_string),
            "^start(salute) {0} I hope you enjoy the showcase ^wait(salute)".format(self.response_string),
        ]

        self.DEFAULT_GREETINGS = [
            "^start(hey) {0} Hello ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Howdy ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Hi ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Hey ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Glad you came ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Welcome ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Welcome in ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Nice to see you here ^wait(hey)".format(self.response_string), 
            "^start(hey) {0} Greetings, I'm Pepper ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Hello, I'm Pepper ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Welcome, I'm Pepper ^wait(hey)".format(self.response_string),
            "^start(hey) {0} Hey, my name is Pepper ^wait(hey)".format(self.response_string),
            "^start(bowshort) {0} Welcome ^wait(bowshort)".format(self.response_string), 
            "^start(bowshort) {0} Welcome in ^wait(bowshort)".format(self.response_string), 
            "^start(bowshort) {0} Nice to see you here ^wait(bowshort)".format(self.response_string), 
            "^start(bowshort) {0} Greetings, I'm Pepper ^wait(bowshort)".format(self.response_string),
            "^start(bowshort) {0} Hello, I'm Pepper ^wait(bowshort)".format(self.response_string),
            "^start(bowshort) {0} Welcome, I'm Pepper ^wait(bowshort)".format(self.response_string),
            "^start(bowshort) {0} Hello, my name is Pepper ^wait(bowshort)".format(self.response_string),
            "^start(salute) {0} Welcome ^wait(salute)".format(self.response_string),
            "^start(salute) {0} Welcome in ^wait(salute)".format(self.response_string),
            "^start(salute) {0} Nice to see you here ^wait(salute)".format(self.response_string)
        ]
        
        self.greetings = self.DEFAULT_GREETINGS

    def __del__(self):
        print("INF: GreetingsModule.__del__: cleaning everything")
        self.stop()
        
    def update_profile(self, event_name, value):
        if "ltq" in value.lower():
            self.greetings = self.LTQ_GREETINGS
            print("INF: GreetingsModule: Updated greetings for LTQ profile")
        elif "north" in value.lower() or "city" in value.lower():
            self.greetings = self.CN_GREETINGS
            print("INF: GreetingsModule: Updated greetings for CityNorth profile")
        else:
            self.greetings = self.DEFAULT_GREETINGS
            print("INF: GreetingsModule: Updated greetings for default profile", value)
    
    def on_control_greetings(self, event_name = None, value = False):
        self.enabled_greetings = value
        print("Received control greetings event")
        print("INF: GreetingsModule: Greetings are", "ON" if value else "OFF")

    def on_greetings_require_face_lost(self, event_name, value):
        self.require_face_lost = value
        print("INF: GreetingsModule: Greetings require face lost is", "ON" if value else "OFF")

    def on_speak_timeout_change(self, event_name, value):
        self.speak_timeout = value
        print("INF: GreetingsModule: Speak timeout changed to", value)

    def on_face_lost_timeout_change(self, event_name, value):
        self.face_lost_timeout = value
        print("INF: GreetingsModule: Face lost timeout changed to", value)

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
                self.face_lost_timer = threading.Timer(self.face_lost_timeout, self.handle_status_change, [False])
                self.face_lost_timer.start()

    def handle_status_change(self, status):
        if not self.enabled_greetings:
            return
        self.face_detected = status
        if not self.require_face_lost:
            self.face_detected = False
        if not status and not self.waiting_for_greeting:
            self.has_been_greeted = False
            print("INF: GreetingsModule: Resetting conversation")

    def say_greeting(self):
        if not self.enabled_greetings:
            return
        print("INF: GreetingsModule: Saying greeting")
        current_time = time.time()
        if current_time - self.last_spoken_time > self.speak_timeout and not (self.require_face_lost and self.has_been_greeted) and not self.waiting_for_greeting:
            self.has_been_greeted = True
            greeting = random.choice(self.greetings)
            self.memory.raiseEvent('Say', greeting)
            self.memory.subscribeToEvent("ALAnimatedSpeech/EndOfAnimatedSpeech", self.getName(), "greeting_finished")
            self.waiting_for_greeting = True
            self.last_spoken_time = current_time
    
    def greeting_finished(self, event_name, value):
        # Consider eye contact seen after greeting to prevent immediate re-greeting if face is lost mid greeting
        self.memory.unsubscribeToEvent("ALAnimatedSpeech/EndOfAnimatedSpeech", self.getName())
        self.waiting_for_greeting = False
        if self.require_face_lost:
            print("INF: GreetingsModule: Greeting finished")
            self.has_been_greeted = True
            self.on_face_detected(None, True)
            self.on_face_detected(None, False) # Start face lost timer in case face is not detected immediately after greeting as face lost is only triggered once on face lost

    def stop(self):
        self.memory.unsubscribeToEvent("FaceDetected", self.getName())
        self.memory.unsubscribeToEvent("ControlGreetings", self.getName())
        self.memory.unsubscribeToEvent("GreetingsRequireFaceLost", self.getName())
        if self.face_lost_timer:
            self.face_lost_timer.cancel()
        print("INF: GreetingsModule: stopped!")
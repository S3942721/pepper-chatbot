import json
import random
import re
from naoqi import ALProxy, ALModule

class BehaviourExecutor(ALModule):
    def __init__(self, name, behaviours_file, sounds_file, nao_ip, nao_port):
        ALModule.__init__(self, name)
        self.BIND_PYTHON(self.getName(), "callback")

        self.behaviours_file = behaviours_file
        self.sounds_file = sounds_file
        self.nao_ip = nao_ip
        self.nao_port = nao_port
        
        self.mute = False
        self.current_volume = 80
        
        self.DEFAULT_RESPONSE_SPEED = 90
        self.response_speed = self.DEFAULT_RESPONSE_SPEED
        self.response_speed_string = "\\\\rspd=" + str(self.response_speed) + "\\\\"
        
        self.DEFAULT_SENTENCE_PAUSE_DURATION = 5
        self.sentence_pause_duration = self.DEFAULT_SENTENCE_PAUSE_DURATION
        self.sentence_pause_string = "\\\\wait=" + str(self.sentence_pause_duration) + "\\\\"
        
        self.response_string = self.response_speed_string + self.sentence_pause_string
        
        self.memory = ALProxy("ALMemory", self.nao_ip, self.nao_port)
        
        self.memory.subscribeToEvent("Sound", name, "on_play_sound")
        self.memory.subscribeToEvent("EyeColour", name, "on_eye_colour")
        self.memory.subscribeToEvent("EyeColourHold", name, "on_eye_colour_hold")
        self.memory.subscribeToEvent("Mute", name, "on_mute")
        self.memory.subscribeToEvent("Volume", name, "volume")
        self.memory.subscribeToEvent("ChangeResponseSpeed", name, "on_response_speed_change")
        self.memory.subscribeToEvent("ChangeSentencePause", name, "on_sentence_pause_change")
        self.memory.subscribeToEvent("ControlContextMovement", name, "on_control_tracking_mode")
        self.memory.subscribeToEvent("ControlEngagement", name, "on_control_engagement_mode")
        self.memory.subscribeToEvent("ControlAwareness", name, "on_control_basic_awareness")
        
        self.led_service = ALProxy('ALLeds')
        
        with open(self.behaviours_file, 'r') as file:
            self.behaviours = json.load(file)
        
        with open(self.sounds_file, 'r') as file:
            self.sounds = json.load(file)

    def sanitize_behaviour_requests(self, chat_response):
        keyword_to_behaviour = {}
        behaviour_triggered = [False]

        def replace_keyword(match):
            keyword = match.group(2)

            if keyword not in keyword_to_behaviour:
                behaviour = next((b for b in self.behaviours if b['behaviour_key'] == keyword), None)
                if behaviour:
                    selected_behaviour = random.choice(behaviour['behaviour_variations'])
                    keyword_to_behaviour[keyword] = selected_behaviour
                    behaviour_triggered[0] = True
                else:
                    return match.group(0)
            return "^{}({})".format(match.group(1), keyword_to_behaviour[keyword])

        sanitized_response = re.sub(r'\^(start|wait|stop|run)\((.*?)\)', replace_keyword, chat_response)
        spoken_response = re.sub(r'\^(start|wait|stop|run)\([^\)]*\)', '', chat_response).strip()
        return sanitized_response, behaviour_triggered[0], spoken_response

    def on_eye_colour_hold(self, _, value):
        self.set_eye_colour(value)

    def on_eye_colour(self, _, value):
        self.set_eye_colour(value)
        self.memory.subscribeToEvent("ALAnimatedSpeech/EndOfAnimatedSpeech", self.getName(), "reset_eye_colour")
        self.memory.subscribeToEvent("StopSpeech", self.getName(), "reset_eye_colour")

    def set_eye_colour(self, colour):
        if '0x' in colour:
            self.led_service.fadeRGB("FaceLeds", colour, 0.5)

        # Value is a string like "blue", so we need to convert it to the hex value
        else:
            colour = colour.lower()
            case = {
                "red": 0xff0000,
                "green": 0x00ff00,
                "blue": 0x0000ff,
                "yellow": 0xffff00,
                "cyan": 0x00ffff,
                "magenta": 0xff00ff,
                "white": 0xffffff,
                "black": 0x000000
            }
            self.led_service.fadeRGB("FaceLeds", case.get(colour, 0x000000), 0.5)

    def reset_eye_colour(self, _, __):
        self.memory.unsubscribeToEvent("ALAnimatedSpeech/EndOfAnimatedSpeech", self.getName())
        self.memory.unsubscribeToEvent("StopSpeech", self.getName())
        self.led_service.fadeRGB("FaceLeds", 0x000000, 0.5)

    def on_play_sound(self, _, value):
        if value:
            self.play_sound(value)

    def play_sound(self, sound_key):
        sound = next((s for s in self.sounds if s['audio_key'] == sound_key), None)
        if sound:
            selected_sound = random.choice(sound['audio_variations'])
            print("Playing sound: {}".format(selected_sound))
            
            try:
                audio_player_service = ALProxy("ALAudioPlayer", self.nao_ip, self.nao_port)
                audio_player_service.playFile(str(selected_sound), 1.0, 0.0)
                return selected_sound
            except Exception as e:
                print("Error playing sound: {}".format(e))
        else:
            print("No sound found for key: '{}'".format(sound_key))
        return

    def sanitize_sound_requests(self, chat_response, play_sound=True):
        def replace_keyword(match):
            keyword = match.group(1)
            if play_sound:
                self.play_sound(keyword)
            return ''

        sanitized_response = re.sub(r'\*\*audio=(.*?)\*\*', replace_keyword, chat_response)
        return sanitized_response

    def sanitize_request(self, chat_response):
        print("Received chat response: {}".format(chat_response))
        
        sanitized_response, behaviour_triggered, spoken_response = self.sanitize_behaviour_requests(chat_response)
        sanitized_response = self.sanitize_sound_requests(sanitized_response)
        spoken_response = self.sanitize_sound_requests(spoken_response, play_sound=False)
        spoken_response = self.response_string + spoken_response
        sanitized_response = self.response_string + sanitized_response
        print("Sanitized response: {}".format(sanitized_response))
        print("Spoken response: {}".format(spoken_response))
        return sanitized_response, behaviour_triggered, spoken_response

    def execute_behaviour(self, behaviour_key):
        behaviour = next((b for b in self.behaviours if b['behaviour_key'] == behaviour_key), None)
        if behaviour:
            selected_behaviour = random.choice(behaviour['behaviour_variations'])
            print("Executing behaviour: {}".format(selected_behaviour))
            
            if not isinstance(selected_behaviour, str):
                selected_behaviour = str(selected_behaviour)

            try:
                animation_player_service = ALProxy("ALAnimationPlayer", self.nao_ip, self.nao_port)
                animation_player_service.run(selected_behaviour, _async=True)
                return selected_behaviour
            except Exception as e:
                print("Error executing behaviour: {}".format(e))
        else:
            print("No behaviour found for key: '{}'".format(behaviour_key))
        return None
    
    def execute_random_behaviour(self, behaviour_keys):
        self.execute_behaviour(random.choice(behaviour_keys))
        
    def get_next_behaviour(self, index=0, previous_bhv_description="<NO DESCRIPTION>"):
        def update_behaviour_description(current_index, description):
            if 0 <= current_index < len(self.behaviours):
                current_description = self.behaviours[current_index].get('action_description', "<NO DESCRIPTION>")
                if current_description == "<NO DESCRIPTION>" or description != "<NO DESCRIPTION>":
                    self.behaviours[current_index]['action_description'] = description
                    with open(self.behaviours_file, 'w') as file:
                        json.dump(self.behaviours, file, indent=4)
                    print("Updated behaviour at index {} with description: {}".format(current_index, description))

        if index > 0 and self.behaviours[index - 1].get('action_description', "<NO DESCRIPTION>") == "<NO DESCRIPTION>":
            update_behaviour_description(index - 1, previous_bhv_description)

        while index < len(self.behaviours):
            behaviour = self.behaviours[index]
            if behaviour.get('action_description', "<NO DESCRIPTION>") == "<NO DESCRIPTION>":
                return "{} ^run({})".format(behaviour['behaviour_key'], behaviour['behaviour_key']), index + 1
            else:
                print("Skipped: {}".format(behaviour['action_description']))
            index += 1

        return None, index

    def volume(self, _, value):
        self.current_volume = value
        audio = ALProxy( "ALAudioDevice")
        audio.setOutputVolume(self.current_volume)
        print("INF: SpeechRecognitionModule: volume set to %s" % self.current_volume)

    def on_mute(self, _, value):
        self.mute = value
        if value:
            audio = ALProxy( "ALAudioDevice")
            audio.setOutputVolume(0)
            print("INF: SpeechRecognitionModule: volume set to 0")
        else:
            self.volume(None, self.current_volume)

    def on_response_speed_change(self, event_name, value):
        self.response_speed = value
        self.response_speed_string = "\\\\rspd=" + str(self.response_speed) + "\\\\"
        self.response_string = self.response_speed_string + self.sentence_pause_string
        print("INF: GreetingsModule: Response speed changed to {}".format(value))
    
    def on_sentence_pause_change(self, event_name, value):
        self.sentence_pause_duration = value
        self.sentence_pause_string = "\\\\wait=" + str(self.sentence_pause_duration) + "\\\\"
        self.response_string = self.response_speed_string + self.sentence_pause_string
        print("INF: GreetingsModule: Sentence pause duration changed to {}".format(value))
    
    def on_control_basic_awareness(self, event_name, value):
        print("Control basic awareness: {}".format(value))
        aba = ALProxy("ALBasicAwareness")
        aba.setEnabled(value)
    
    def on_control_engagement_mode(self, event_name, value):
        aba = ALProxy("ALBasicAwareness")
        mode = "FullyEngaged" if value else "Unengaged"
        print("Control engagement mode: {}".format(mode))
        aba.setEngagementMode(mode)

    def on_control_tracking_mode(self, event_name, value):
        aba = ALProxy("ALBasicAwareness")
        mode = "MoveContextually" if value else "WholeBody"
        print("Control tracking mode: {}".format(mode))
        aba.setTrackingMode(mode)
from module_receiver import BaseSpeechReceiverModule
from module_speechrecognition import SpeechRecognitionModule
from module_eyecontact import EyeContactModule
from module_greetings import GreetingsModule
from module_healthy_check import HealthyCheckModule
from module_socket import SocketClient
from module_expressions import BehaviourExecutor
from module_motion import MotionModule
from module_exploration import ExploringModule
from module_audiostream import AudioStreamModule

from naoqi import ALProxy, ALBroker
import time
import os
import sys

from optparse import OptionParser
from tools import load_env, toint, tofloat

load_env()

NAO_IP = os.getenv('NAO_IP') or "localhost"
NAO_PORT = toint(os.getenv('NAO_PORT')) or 9559
DEFAULT_VOLUME = toint(os.getenv('DEFAULT_VOLUME')) or 80
DEFAULT_WELCOME = os.getenv('DEFAULT_WELCOME') or "False"
DEFAULT_URL = os.getenv('DEFAULT_URL') or "event-agenda-ltq.html"

# server
URL = os.getenv('URL')
CHAT_COMPLETION_ROUTE = os.getenv('CHAT_COMPLETION_ROUTE') or "/chat/completions"
SPEECH_RECOGNITION_ROUTE = os.getenv('SPEECH_RECOGINITION_ROUTE') or '/speech/recognition'
DEFAULT_SOCKET_URL = os.getenv('DEFAULT_SOCKET_URL') or '192.168.1.101'
DEFAULT_SOCKET_PORT = os.getenv('DEFAULT_SOCKET_PORT') or '3456'
DEFAULT_AUDIO_STREAM_URL = os.getenv('DEFAULT_AUDIO_STREAM_URL') or '192.168.1.101'
DEFAULT_AUDIO_STREAM_PORT = os.getenv('DEFAULT_AUDIO_STREAM_PORT') or '5004'
DEFAULT_WEB_CONTROLLER_URL = os.getenv('DEFAULT_WEB_CONTROLLER_URL') or None

# openai
MODEL_NAME = os.getenv('MODEL_NAME')
API_KEY = os.getenv('API_KEY')
SPEECH_API_KEY = os.getenv('SPEECH_API_KEY') or API_KEY

WEBVIEW = os.getenv('WEBVIEW') or "http://198.18.0.1/apps/rmit-race/event-agenda-ltq.html"

def main():
    parser = OptionParser()
    parser.add_option("--volume",
        help="The volume of the robot, default 50",
        dest="volume")
    parser.add_option("--ip",
        help="Parent broker port. The IP address or your robot",
        dest="ip")
    parser.add_option("--port",
        help="Parent broker port. The port NAOqi is listening to",
        dest="port",
        type="int")
    parser.add_option("--url",
        help="Base url of OpenAI-llike Server",
        dest="server_url")
    parser.add_option("--chat-route",
        help="Route of chat completion service, default '/chat/completions'",
        dest="chat_route")
    parser.add_option("--speech-route",
        help="Route of speech recognition service, default '/speech/recognition'",
        dest="speech_route")
    parser.add_option("--api-key",
        help="API Key of services",
        dest="api_key")
    parser.add_option("--speech-api-key",
        help="API Key of Speech Service, default to the same of --api-key option",
        dest="speech_api_key")
    parser.add_option("--model-name",
        help="Model name when calling OpenAI API",
        dest="model_name")
    parser.add_option("--save-csv",
        help="Set to enable save conversation to a file called dialogue.csv",
        dest="save_csv",
        action='store_true')
    parser.add_option("--prompt",
        help="Add a system prompt",
        dest="prompt")
    parser.add_option("--welcome",
        help="Enable the welcome message",
        dest="welcome")
    parser.add_option("--fprompt",
        help="Add a system prompt load from a file, specify the file name to . If --prompt is specified, ignore this",
        dest="fprompt")
    parser.add_option("--fbehaviours",
        help="Add a system behaviour json file, specify the file name.",
        dest="fbehaviours")
    parser.add_option("--fsounds",
        help="Add a system sounds json file, specify the file name.",
        dest="fsounds")
    parser.add_option("--webview",
        help="Start a webview server when this script starts. Speficy the url of webview.",
        dest="webview")
    parser.add_option("--socket-url",
        help="URL of the server running the pepper-controller.",
        dest="socket_url")
    parser.add_option("--socket-port",
        help="Port of the server running the pepper-controller.",
        dest="socket_port")
    parser.add_option("--audio-stream-url",
        help="URL for audio streaming.",
        dest="audio_stream_url")
    parser.add_option("--audio-stream-port",
        help="Port for audio streaming.",
        dest="audio_stream_port")
    parser.add_option("--web-controller-url",
        help="Base URL of the web controller (serves as both socket and audio stream URL unless overridden).",
        dest="web_controller_url")
    parser.set_defaults(
        volume=DEFAULT_VOLUME,
        ip=NAO_IP,
        port=NAO_PORT,
        server_url=URL,
        chat_route=CHAT_COMPLETION_ROUTE,
        speech_route=SPEECH_RECOGNITION_ROUTE,
        api_key=API_KEY,
        speech_api_key=SPEECH_API_KEY,
        model_name=MODEL_NAME,
        save_csv=False,
        prompt='',
        welcome=DEFAULT_WELCOME,
        fprompt='',
        fbehaviours='/home/nao/pepperchat/behaviours/behaviours_described.json',
        fsounds='/home/nao/pepperchat/media/sounds_described.json',
        webview=WEBVIEW,
        socket_url=DEFAULT_SOCKET_URL,
        socket_port=DEFAULT_SOCKET_PORT,
        audio_stream_url=DEFAULT_AUDIO_STREAM_URL,
        audio_stream_port=DEFAULT_AUDIO_STREAM_PORT,
        web_controller_url=DEFAULT_WEB_CONTROLLER_URL
    )

    opts = parser.parse_args()[0]

    volume = toint(opts.volume)
    ip   = opts.ip
    port = toint(opts.port)
    server_url = opts.server_url
    chat_route = opts.chat_route
    speech_route = opts.speech_route
    api_key = opts.api_key
    speech_api_key = opts.speech_api_key
    model_name = opts.model_name
    save_csv = opts.save_csv
    prompt=opts.prompt
    fprompt=opts.fprompt
    fbehaviours=opts.fbehaviours
    fsounds=opts.fsounds
    webview = opts.webview
    socket_url = opts.socket_url
    socket_port = opts.socket_port
    audio_stream_url = opts.audio_stream_url
    audio_stream_port = opts.audio_stream_port
    web_controller_url = opts.web_controller_url

    # URL resolution logic
    # 1. If web controller URL is provided, use it as base for both socket and audio streaming
    # 2. Specific socket_url or audio_stream_url override the web controller URL
    if web_controller_url:
        print("Using web controller URL: {}".format(web_controller_url))
        
        # Use web controller URL for socket if not specifically overridden
        if socket_url == DEFAULT_SOCKET_URL:
            socket_url = web_controller_url
            print("Socket URL set from web controller: {}".format(socket_url))
        
        # Use web controller URL for audio streaming if not specifically overridden
        if audio_stream_url == DEFAULT_AUDIO_STREAM_URL:
            audio_stream_url = web_controller_url
            print("Audio stream URL set from web controller: {}".format(audio_stream_url))

    # Display final configuration
    print("Final configuration:")
    print("  Socket URL: {}:{}".format(socket_url, socket_port))
    print("  Audio Stream: {}:{}".format(audio_stream_url, audio_stream_port))

    # if not server_url:
    #     print('Error: Services route not specified!')
    #     return
    
    try:
        if not prompt and fprompt:
            prompt_file = open(fprompt, 'r')
            prompt = prompt_file.read().strip()
            prompt_file.close()
    except:
        print('\n\nLoading prompt failed, does the file exists? Using the default, blank prompt...\n\n')
        prompt = ''

    # setup broker to use memory and different modules
    myBroker = ALBroker("myBroker",
       "0.0.0.0", # listen to anyone
       0,         # find a free port and use it
       ip,        # parent broker IP
       port       # parent broker port
    )

    try:
        p = ALProxy("SpeechRecognition")
        p.exit()  # kill previous instance, useful for developing ;)
    except:
        pass
    
    asr = ALProxy("ALSpeechRecognition")
    asr.setAudioExpression(False)
    asr.setVisualExpression(False)
    
    # Set all LEDs to white
    led_service = ALProxy('ALLeds')
    led_service.fadeRGB('AllLeds', 0xffffff, 0.5)
    
    audio = ALProxy( "ALAudioDevice")
    audio.setOutputVolume(volume)
    print("INF: SpeechRecognitionModule: volume set to %s" % volume)
    
    aba = ALProxy("ALBasicAwareness")
    aba.setEnabled(True)
    aba.setEngagementMode("FullyEngaged") # Unengaged, FullyEngaged, SemiEngaged TODO: tweak this
    aba.setTrackingMode("WholeBody") # Head, WholeBody, MoveContextually, BodyRotation TODO: tweak this
    
    # declear events sharing between different modules
    memory = ALProxy("ALMemory")
    memory.declareEvent("SpeechRecognition")
    memory.declareEvent("ClearSpeechRecognitionBuffer")
    memory.declareEvent("Speaking")
    memory.declareEvent("PepperMessage")
    memory.declareEvent("Log")
    memory.declareEvent("Listening")
    memory.declareEvent("UserMessage")
    memory.declareEvent("EyeContact")
    memory.declareEvent("RunningBehaviour")
    memory.declareEvent("ResetConversation")
    memory.declareEvent("HealthyCheck")
    memory.declareEvent("ControlRecording")
    memory.declareEvent("Sync")
    memory.declareEvent("SyncMessages")
    memory.declareEvent("LoadHTML")
    memory.declareEvent("TriggerGapFill")
    memory.declareEvent("Say")
    memory.declareEvent("JSONSay")
    memory.declareEvent("SayChunk")
    memory.declareEvent("ControlGreetings")
    memory.declareEvent("GreetingsRequireFaceLost")
    memory.declareEvent("StopSpeech")
    memory.declareEvent("StopAction")
    memory.declareEvent("StopAll")
    memory.declareEvent("StopBehaviour")
    memory.declareEvent("StopAudio")
    memory.declareEvent("UpdateProfile")
    memory.declareEvent("ChangeGreetFaceLostTimeout")
    memory.declareEvent("ChangeGreetTimeout")
    memory.declareEvent("ChangeResponseSpeed")
    memory.declareEvent("ChangeSentencePause")
    memory.declareEvent("ControlContextMovement")
    memory.declareEvent("ControlAwareness")
    memory.declareEvent("ControlEngagement")
    memory.declareEvent("ControlMovement")
    memory.declareEvent("Move")
    memory.declareEvent("ContinuousMove")
    memory.declareEvent("ControlExploration")
    memory.declareEvent("ControlWandering")
    memory.declareEvent("LockHead")
    memory.declareEvent("ControlUDPAudioStreaming")

    # turn off native pepper speech recognition
    asr = ALProxy("ALSpeechRecognition", ip, port)
    asr.setVisualExpression(False)  # disable LEDs for when speech is detected (spinning blue eyes)
    asr.setAudioExpression(False)   # disable beep noise when speech is detected

    speech_recoginition_url = os.getenv('SPEECH_RECOGINITION_URL') or server_url

    # Initialize speech recognition module with proper audio configuration
    global SpeechRecognition
    SpeechRecognition = SpeechRecognitionModule(
        "SpeechRecognition", ip, port,
        speech_recoginition_url, speech_route, speech_api_key, volume
    )

    global EyeContact
    EyeContact = EyeContactModule("EyeContact")

    # auto-detection configuration (commented out since we're using for audio streaming)
    # SpeechRecognition.setHoldTime(tofloat(os.getenv('HOLD_TIME')) or 2.0)
    # SpeechRecognition.setIdleReleaseTime(tofloat(os.getenv('RELEASE_TIME')) or 1.0)
    # SpeechRecognition.setMaxRecordingDuration(tofloat(os.getenv('RECORD_DURATION')) or 7.0)
    # SpeechRecognition.setLookaheadDuration(tofloat(os.getenv('LOOK_AHEAD_DURATION')) or 0.5)
    # SpeechRecognition.setAutoDetectionThreshold(toint(os.getenv('AUTO_DETECTION_THREADSHOLD')) or 5)
    # SpeechRecognition.enableAutoDetection()
    
    # Start speech recognition for audio capture (always on for streaming)
    SpeechRecognition.start()

    global Expressions
    Expressions = BehaviourExecutor("Expressions", fbehaviours, fsounds, ip, port)

    global Receiver
    Receiver = BaseSpeechReceiverModule(
        "Receiver", ip, port,
        server_url=server_url, base_route=chat_route,
        api_key=api_key, model_name=model_name, save_csv=save_csv,
        system_prompt=prompt, expressions=Expressions
    )
    Receiver.start()
    
    global Greetings
    Greetings = GreetingsModule("Greetings")
    
    if opts.welcome == "True":
        Greetings.on_control_greetings(value=True)

    # if webview:
    global HealthyCheck
    HealthyCheck = HealthyCheckModule("HealthyCheck", webview_url=webview)
    
    global Motion
    Motion = MotionModule("Motion", ip, port)

    global Exploration
    Exploration = ExploringModule("Exploration")    

    # Initialize GStreamer audio streaming module with resolved URLs
    global AudioStream
    AudioStream = AudioStreamModule(
        "AudioStream", ip, port,
        audio_stream_url, toint(audio_stream_port)
    )
    
    socket_client = SocketClient(socket_url, toint(socket_port))
    # Connect speech recognition module to socket client for audio streaming
    socket_client.set_speech_module(SpeechRecognition)
    socket_client.start()

    # memory.raiseEvent("Say", "**audio=quickbells**")
    # memory.raiseEvent("Say", "Goodbye everyone, and just remember ^start(you) $EyeColour=red $Sound=ill_be_back $EyeColour=red ^wait(you) \\\\pau=1000\\\\")
    # memory.raiseEvent("Say", "^run(helicopter) $EyeColour=red $Sound=get_to_the_choppa $EyeColour=red")

    # Load the default HTML for logo
    memory.raiseEvent("LoadHTML", webview)
    # memory.raiseEvent("LoadHTML", "http://198.18.0.1/apps/rmit-race/event-agenda-ltq.html")
    print("I am alive.")

    try:
        while True:
            time.sleep(1)
            if webview:
                HealthyCheck.ping()

    except KeyboardInterrupt:
        print()
        print("Interrupted by user, shutting down")
        memory.raiseEvent("StopAction", None)
        time.sleep(1)
        myBroker.shutdown()
        socket_client.join()
        sys.exit(0)

if __name__ == "__main__":
    main()

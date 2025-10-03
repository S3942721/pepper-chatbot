import os
import sys
import time
import subprocess
import logger
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
from module_speaking_manager import SpeakingStateManager
from module_awareness import AwarenessModule

from naoqi import ALProxy, ALBroker

from optparse import OptionParser
from tools import load_env, toint, tofloat

load_env()

NAO_IP = os.getenv('NAO_IP') or "localhost"
NAO_PORT = toint(os.getenv('NAO_PORT')) or 9559
DEFAULT_VOLUME = toint(os.getenv('DEFAULT_VOLUME')) or 60
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
DEFAULT_WAKE_ON_START = os.getenv('DEFAULT_WAKE_ON_START') or "True"
DEFAULT_REST_ON_EXIT = os.getenv('DEFAULT_REST_ON_EXIT') or "False"

# openai
MODEL_NAME = os.getenv('MODEL_NAME')
API_KEY = os.getenv('API_KEY')
SPEECH_API_KEY = os.getenv('SPEECH_API_KEY') or API_KEY

WEBVIEW = os.getenv('WEBVIEW') or "http://198.18.0.1:3000/tablet?robot=Haku"

def main():
    # Setup logger first with default level - will be reconfigured later
    logger.setup_logging(logger.VERBOSE)

    parser = OptionParser()
    parser.add_option("--volume",
        help="The volume of the robot, default {}".format(DEFAULT_VOLUME),
        dest="volume")
    parser.add_option("--ip",
        help="Parent broker port. The IP address or your robot, ONLY if running off-robot",
        dest="ip")
    parser.add_option("--port",
        help="Parent broker port. The port NAOqi is listening to, default {}".format(NAO_PORT),
        dest="port",
        type="int")
    parser.add_option("--url",
        help="Base url of OpenAI-like Server",
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
    parser.add_option("--log-level",
        help="Set logging level (FATAL=5, ERROR=4, WARNING=3, INFO=2, VERBOSE=1, DEBUG=0). Lower numbers show more detail. Default: INFO",
        dest="log_level")
    parser.add_option("--log-filter",
        help="Set log filters using qi.logging filter syntax (e.g., 'qi.*=verbose:-qi.foo:+qi.foo.bar') or to target only specific module: '+module_receiver'",
        dest="log_filter")
    parser.add_option("--filter-qitype",
        help="Filter out qitype.metaobject warning messages (default: True)",
        dest="filter_qitype",
        action="store_false",
        default=True)
    parser.add_option("--early-speaking-finish",
        help="Enable early speaking finish detection for trailing behaviors (default: True)",
        dest="early_speaking_finish",
        action="store_false",
        default=True)
    parser.add_option("--wake-on-start",
        help="Wake robot on startup (default: True)",
        dest="wake_on_start")
    parser.add_option("--rest-on-exit",
        help="Put robot to rest on program exit (default: False)",
        dest="rest_on_exit")
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
        web_controller_url=DEFAULT_WEB_CONTROLLER_URL,
        log_level="INFO",
        log_filter="",
        filter_qitype=True,
        wake_on_start=DEFAULT_WAKE_ON_START,
        rest_on_exit=DEFAULT_REST_ON_EXIT
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
    log_level_str = opts.log_level.upper()
    log_filter = opts.log_filter
    filter_qitype = opts.filter_qitype
    early_speaking_finish = opts.early_speaking_finish
    wake_on_start = opts.wake_on_start == "True"  # Convert string to boolean
    rest_on_exit = opts.rest_on_exit == "True"    # Convert string to boolean

    # Configure logging with specified level and filters
    log_level_map = {
        "FATAL": logger.FATAL,
        "ERROR": logger.ERROR, 
        "WARNING": logger.WARNING,
        "INFO": logger.INFO,
        "VERBOSE": logger.VERBOSE,
        "DEBUG": logger.DEBUG
    }
    
    # Set log level
    log_level = log_level_map.get(log_level_str, logger.INFO)
    logger.setup_logging(log_level)
    
    # Build filter string
    filter_parts = []
    
    # Add qitype filter if enabled
    if filter_qitype:
        filter_parts.append("-qitype.metaobject")
        filter_parts.append("-alcommon.autobind")
        filter_parts.append("-qimessaging.server")
        filter_parts.append("-qimessaging.transportsocket")

    # Add user-specified filters
    if log_filter:
        filter_parts.append(log_filter)
    
    # Apply filters if any are specified
    if filter_parts:
        import qi
        combined_filter = ":".join(filter_parts)
        qi.logging.setFilters(combined_filter)
        logger.info("Applied log filters: ", combined_filter)
    
    logger.info("Log level set to: ", log_level_str,"(",log_level,")")

    # URL resolution logic
    # 1. If web controller URL is provided, use it as base for both socket and audio streaming
    # 2. Specific socket_url or audio_stream_url override the web controller URL
    if web_controller_url:
        logger.info("Using web controller URL:", web_controller_url)
        
        # Use web controller URL for socket if not specifically overridden
        if socket_url == DEFAULT_SOCKET_URL:
            socket_url = web_controller_url
            logger.info("Socket URL set from web controller:", socket_url)
        
        # Use web controller URL for audio streaming if not specifically overridden
        if audio_stream_url == DEFAULT_AUDIO_STREAM_URL:
            audio_stream_url = web_controller_url
            logger.info("Audio stream URL set from web controller:", audio_stream_url)

    # Configure Pepper tablet proxy target if webview is enabled
    def _extract_host(value):
        try:
            v = str(value or '').strip()
            if not v:
                return None
            if '://' not in v:
                v = 'http://' + v
            
            # Manual parsing without urlparse
            try:
                after_scheme = v.split('://', 1)[1]
                hostport = after_scheme.split('/', 1)[0]
                host = hostport.split(':', 1)[0]
                return host or None
            except Exception:
                return None
        except Exception:
            return None

    
    proxy_target_host = None
    if webview:
        # Prefer web_controller_url host, then socket_url, then audio_stream_url
        proxy_target_host = _extract_host(web_controller_url) or _extract_host(socket_url) or _extract_host(audio_stream_url)
        # Avoid setting to Pepper's own proxy IP or localhost
        if proxy_target_host in [None, '198.18.0.1', '127.0.0.1', 'localhost']:
            proxy_target_host = None
        
        if proxy_target_host:
            try:
                logger.info("Setting tablet proxy target host to:", proxy_target_host)
                rc = subprocess.call(['pepper-proxy-ctl', 'set-target', proxy_target_host])
                if rc == 0:
                    logger.info("pepper-proxy-ctl set-target succeeded")
                else:
                    logger.warning("pepper-proxy-ctl returned non-zero exit code:", rc)
            except OSError as e:
                logger.warning("pepper-proxy-ctl not available or failed to execute:", e)

    # Display final configuration
    logger.info("Final configuration:")
    logger.info("  Socket URL: ", socket_url, ":", socket_port)
    logger.info("  Audio Stream: ", audio_stream_url, ":", audio_stream_port)

    # if not server_url:
    #     logger.error('Error: Services route not specified!')
    #     return
    
    try:
        if not prompt and fprompt:
            prompt_file = open(fprompt, 'r')
            prompt = prompt_file.read().strip()
            prompt_file.close()
    except:
        logger.warning('Loading prompt failed, does the file exists? Using the default, blank prompt...')
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
    logger.info("SpeechRecognitionModule: volume set to", volume)
    
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
    memory.declareEvent("ControlAudioStreaming")
    memory.declareEvent("ReloadTablet")
    memory.declareEvent("WebviewHeartbeat")
    
    # Robot awareness events
    memory.declareEvent("ControlRobotWake")
    memory.declareEvent("ControlRobotRest")
    memory.declareEvent("GetRobotAwarenessStatus")
    memory.declareEvent("RobotAwarenessState")
    
    # Speaking manager events
    memory.declareEvent("StartSpeaking")
    memory.declareEvent("StopSpeaking")
    memory.declareEvent("QueueSpeech")
    memory.declareEvent("DequeueResult")

    # turn off native pepper speech recognition
    asr = ALProxy("ALSpeechRecognition", ip, port)
    asr.setVisualExpression(False)  # disable LEDs for when speech is detected (spinning blue eyes)
    asr.setAudioExpression(False)   # disable beep noise when speech is detected

    speech_recoginition_url = os.getenv('SPEECH_RECOGINITION_URL') or server_url

    # Initialize speaking state manager first (before other modules that depend on Speaking events)
    global SpeakingManager
    SpeakingManager = SpeakingStateManager("SpeakingManager")

    logger.info("Initialising core modules with pre-cached proxies...")

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
        system_prompt=prompt, expressions=Expressions, 
        early_speaking_finish=early_speaking_finish
    )
    Receiver.start()
    
    global Greetings
    Greetings = GreetingsModule("Greetings")
    
    if opts.welcome == "True":
        Greetings.on_control_greetings(value=True)

    # if webview:
    global HealthyCheck
    HealthyCheck = HealthyCheckModule("HealthyCheck", nao_ip=ip, nao_port=port, webview_url=webview)
    
    global Motion
    Motion = MotionModule("Motion", ip, port)

    global Exploration
    Exploration = ExploringModule("Exploration")    

    # Initialize Robot Awareness Module with configuration options
    global RobotAwareness
    RobotAwareness = AwarenessModule("RobotAwareness", ip, port, wake_on_start, rest_on_exit)

    # Initialize GStreamer audio streaming module with resolved URLs
    global AudioStream
    AudioStream = AudioStreamModule(
        "AudioStream", ip, port,
        audio_stream_url, toint(audio_stream_port)
    )

    global SocketClient
    SocketClient = SocketClient(
        "SocketClient", ip, port,
        socket_url, toint(socket_port)
    )
    # Connect speech recognition module to socket client for audio streaming
    SocketClient.start()

    # Load the default HTML for logo
    memory.raiseEvent("LoadHTML", webview)
    # memory.raiseEvent("LoadHTML", "http://198.18.0.1/apps/rmit-race/event-agenda-ltq.html")
    logger.info("I am alive.")

    logger.info("Add empty say to spawn speech threads")
    memory.raiseEvent("Say", "")

    try:
        while True:
            time.sleep(1)
            # if webview:           # TODO: Find a way that works for checking if the tablet has gone away
                # HealthyCheck.ping()
                # logger.debug("TURNED OFF PING FOR WEBVIEW HEALTHY CHECK")

    except KeyboardInterrupt:
        logger.info("")
        logger.info("Interrupted by user, shutting down gracefully...")
        
        # # Stop socket client first
        # try:
        #     logger.info("Stopping socket client...")
        #     SocketClient.stop()
        # except:
        #     pass

        # Clean up modules by removing references and letting __del__ handle cleanup
        try:
            logger.info("Cleaning up modules...")
            # Remove global references to trigger __del__ methods
            if 'SocketClient' in globals():
                del SocketClient
            if 'AudioStream' in globals():
                del AudioStream
            if 'SpeechRecognition' in globals():
                del SpeechRecognition
            if 'Receiver' in globals():
                del Receiver
            if 'Greetings' in globals():
                del Greetings
            if 'Expressions' in globals():
                del Expressions
            if 'EyeContact' in globals():
                del EyeContact
            if 'Motion' in globals():
                del Motion
            if 'Exploration' in globals():
                del Exploration
            if 'HealthyCheck' in globals():
                del HealthyCheck
            if 'SpeakingManager' in globals():
                del SpeakingManager
            if 'RobotAwareness' in globals():
                del RobotAwareness
        except Exception as e:
            logger.error("Error during module cleanup:", e)
        
        # Give modules time to clean up
        logger.info("Waiting for modules to clean up...")
        time.sleep(2)
        
        logger.info("Shutting down broker...")
        myBroker.shutdown()
        sys.exit(0)

if __name__ == "__main__":
    main()

# Pepper Chatbot / Haku Robot Handler

The on-robot execution layer for Haku's control and conversation system. This Python 2.7 application uses Pepper's NAOqi services to turn remote commands and streamed conversation responses into speech, gestures, motion, and tablet updates, while reporting robot state back to the controller.

It can also call OpenAI-compatible HTTP services for speech recognition and chat completion. In the integrated local-LLM setup, STT and inference run on external hosts and the controller sends responses to this handler.

## Features

- Queued text-to-speech with embedded animation, LED, and sound commands.
- Behaviour sanitisation and automatic waits for animations marked `must_complete`.
- TCP command reception, robot identification, and speaking/listening state reporting.
- Robot microphone capture and GStreamer RTP streaming to an external STT server.
- Movement, head control, awareness, wake/rest, and exploration modules.
- Tablet webview loading and health monitoring.
- Configurable module logging and optional conversation CSV output.

## Requirements

**On Pepper:** Python 2.7, `naoqi`, `qi`, NumPy, and the GStreamer tools/plugins used by the audio sender. NAOqi comes from the robot runtime or a matching SDK; `requirements.txt` only lists NumPy and does not install the robot SDK. Use dependencies compatible with Pepper's existing runtime rather than installing current Python 3 packages on the robot.

**On the deployment workstation:** Python 3, SSH tools (`ssh`, `ssh-keygen`, `ssh-copy-id`, `scp`), and preferably rsync. The `pepper_sync` helper uses Python 3; the application under `src/` uses Python 2.7. These are separate runtimes.

Pepper and the service hosts must be reachable across the network, and the behaviours referenced by your scripts must be installed on the robot. Startup wakes the robot by default; use an appropriate clear operating area for motion and gestures.

## Clone and deploy

```bash
git clone https://github.com/S3942721/pepper-chatbot.git
cd pepper-chatbot
python3 pepper_sync --setup 192.168.1.100
python3 pepper_sync --all
ssh haku
```

Replace the example IP with Pepper's address. SSH setup creates a robot key and a `haku` host entry on your workstation; provide the robot's configured password when prompted.

The helper copies **the contents of `src/`** to `/home/nao/pepperchat`. Media is opt-in on ordinary syncs. `--all` also synchronises HTML, media, and the bundled hands-above-head behaviour files. Copying behaviour files does not guarantee every behaviour in the catalogue is installed and runnable.

| Command | Purpose |
| --- | --- |
| `python3 pepper_sync` | Sync source using the existing SSH configuration |
| `python3 pepper_sync 192.168.1.100` | Sync using a new robot address |
| `python3 pepper_sync --media` | Include sound/video assets |
| `python3 pepper_sync --html` | Include root HTML pages |
| `python3 pepper_sync --hands-above-head` | Copy the bundled behaviour files |
| `python3 pepper_sync --set-ip 192.168.1.100` | Update the robot SSH host configuration |
| `python3 pepper_sync --use-scp` | Use scp instead of rsync |
| `python3 pepper_sync --help` | Show all deployment options |

`--delete` removes the deployed application folder before syncing; ordinary updates do not require it. HTML deployment paths and the SSH alias are defined in `pepper_sync` and reflect the original robot installation.

## Start on Pepper

After logging into the robot:

```bash
cd /home/nao/pepperchat
python start.py \
  --socket-url 192.168.1.10 --socket-port 3456 \
  --audio-stream-url 192.168.1.10 --audio-stream-port 5004 \
  --webview 'http://192.168.1.10:3000/tablet?robot=Haku' \
  --log-level INFO
```

Here `192.168.1.10` is a workstation hosting both the web controller and STT. Point `--socket-url` at the **controller host** and `--audio-stream-url` at the **STT host** if they differ. These flags accept a hostname or IP, without `http://`, a port, or a path; the socket client uses plain TCP and the audio sender uses UDP.

`--web-controller-url` can set both destination hosts when services share a machine, but also needs a bare hostname/IP for those connections. Explicit socket/audio destinations allow separate hosts. `--webview` is a full HTTP URL.

For execution from a source checkout on a compatible NAOqi workstation, the entry point is `python src/start.py --ip ROBOT_IP`. Set `--fbehaviours` and `--fsounds` to local files because their defaults point at the robot deployment folder. The normal deployment runs on Pepper with `NAO_IP=localhost` and `NAO_PORT=9559`.

Stop with Ctrl+C. Lifecycle settings accept the literal strings `True` or `False`:

```bash
python start.py --socket-url 192.168.1.10 \
  --audio-stream-url 192.168.1.10 \
  --wake-on-start False --rest-on-exit True --log-level DEBUG
```

## Configuration

`start.py` reads `.env` from the **current working directory**. This is a simple `KEY=value` loader, not a full dotenv parser: use unquoted values without inline comments or additional `=` characters. The sync helper does not copy a repository-root `.env` into the robot folder; create it there if needed. Command-line options override the loaded defaults.

| Option | Environment variable | Purpose / default |
| --- | --- | --- |
| `--ip`, `--port` | `NAO_IP`, `NAO_PORT` | NAOqi parent; `localhost`, `9559` |
| `--socket-url`, `--socket-port` | `DEFAULT_SOCKET_URL`, `DEFAULT_SOCKET_PORT` | Controller TCP host; port `3456` |
| `--audio-stream-url`, `--audio-stream-port` | `DEFAULT_AUDIO_STREAM_URL`, `DEFAULT_AUDIO_STREAM_PORT` | STT RTP host; port `5004` |
| `--web-controller-url` | `DEFAULT_WEB_CONTROLLER_URL` | Shared controller/audio host when appropriate |
| `--webview` | `WEBVIEW` | Full tablet page URL |
| `--volume` | `DEFAULT_VOLUME` | Speech volume; `60` |
| `--url`, `--model-name` | `URL`, `MODEL_NAME` | Optional OpenAI-compatible service base URL and model |
| `--api-key`, `--speech-api-key` | `API_KEY`, `SPEECH_API_KEY` | Optional HTTP service credentials |
| `--wake-on-start`, `--rest-on-exit` | `DEFAULT_WAKE_ON_START`, `DEFAULT_REST_ON_EXIT` | Defaults `True`, `False` |
| `--save-csv` | — | Write conversation logs to `dialogue.csv` |
| `--log-level`, `--log-filter` | — | Logging level and qi module filters |
| `--fbehaviours`, `--fsounds`, `--fprompt` | — | Behaviour catalogue, sound catalogue, optional prompt file |

The HTTP client defaults to `/chat/completions` and `/speech/recognition` routes. These are separate from the streaming STT WebSocket and native Ollama API. Historical speech environment variables are spelled `SPEECH_RECOGINITION_URL` and `SPEECH_RECOGINITION_ROUTE` in the code; retain that spelling if using them. Do not put service credentials in tracked files.

The default tablet URL uses `198.18.0.1`, Pepper's tablet-side network. It depends on a robot-side proxy arrangement. Startup attempts to configure `pepper-proxy-ctl` when available, but this repository does not install that tool. Use a directly reachable controller URL or configure your robot's tablet proxy separately.

## Architecture

Modules communicate through NAOqi `ALMemory` events. `start.py` creates the broker, declares events, initialises shared services, and starts the receiver/socket workers.

| File | Responsibility |
| --- | --- |
| [src/start.py](src/start.py) | Startup, CLI configuration, module wiring, and shutdown |
| [src/module_socket.py](src/module_socket.py) | TCP transport, commands, identification, and status |
| [src/module_receiver.py](src/module_receiver.py) | Speech queue, response processing, and optional HTTP inference |
| [src/module_expressions.py](src/module_expressions.py) | Behaviour markup, animations, LEDs, and sounds |
| [src/module_speaking_manager.py](src/module_speaking_manager.py) | Speech lifecycle and queue coordination |
| [src/module_speechrecognition.py](src/module_speechrecognition.py) | Microphone capture and optional HTTP recognition |
| [src/module_audiostream.py](src/module_audiostream.py) | GStreamer RTP audio sender |
| [src/module_motion.py](src/module_motion.py) | Movement and head-control commands |
| [src/module_awareness.py](src/module_awareness.py) | Robot awareness and wake/rest state |
| [src/module_healthy_check.py](src/module_healthy_check.py) | Tablet loading and health handling |
| [src/logger.py](src/logger.py) | qi logging and module filters |

Important events include `Say` / `JSONSay`, `StartSpeaking` / `StopSpeaking`, `Speaking`, `QueueSpeech` / `DequeueResult`, `ControlRecording`, `RunningBehaviour`, `Move`, `ControlAudioStreaming`, and `ReloadTablet`.

Despite its name, `module_socket.py` is **not a WebSocket client**. It identifies as `Haku` using a `robot-identify` JSON message. For another robot, adapt the identity in this module and match the controller's robot mapping.

## Behaviour markup

Speech may include commands resolved against [src/robot_behaviours_described.json](src/robot_behaviours_described.json):

| Markup | Effect |
| --- | --- |
| `^start(name)` | Start an animation alongside speech |
| `^run(name)` | Run an animation synchronously |
| `^wait(name)` | Wait for a started animation |
| `^stop(name)` | Stop the named animation |

```text
Hello! ^start(hey) Nice to meet you. ^wait(hey)
```

For behaviours marked `must_complete: true`, the sanitiser inserts a missing wait before the next start command or at the end of the response. Catalogue names must resolve to installed robot behaviours. Sound definitions live in [src/media/sounds_described.json](src/media/sounds_described.json); the deployment needs their associated media files.

To add a behaviour, add or update its catalogue definition, install the robot behaviour, update any prompt/script that refers to it, sync the relevant files, and test a short command before using it in a conversation.

## Verification and troubleshooting

- **Robot missing from the controller:** check the bare TCP destination host and port `3456`, then look for the connection and `robot-identify` log messages. The current handler reports `Haku`.
- **No STT audio:** confirm the audio stream targets the STT machine, UDP `5004` is reachable, and STT is running in `remote` mode. The sender/receiver RTP format is L16, mono, 44.1 kHz; STT resamples to 16 kHz.
- **Speech works but gestures fail:** check installed behaviour paths, the catalogue passed by `--fbehaviours`, and whether required sound files were synced.
- **Tablet blank:** check the full webview URL from the tablet's network, proxy availability, and the controller's tablet status endpoint.
- **Import errors:** run with Pepper's Python 2.7/NAOqi environment; installing the workstation's Python dependencies does not provide the robot runtime.
- **Detailed logs:** use `--log-level DEBUG --log-filter '+module_receiver:+module_socket'`. CSV logs require `--save-csv` and are written relative to the working directory.

On Pepper, inspect the runtime without issuing a motion command:

```bash
python -c "from naoqi import ALProxy; print(ALProxy('ALAudioDevice', 'localhost', 9559).getOutputVolume())"
python start.py --help
```

Hardware validation requires a Pepper robot and reachable service hosts. The `src/test/` and audio test scripts are manual utilities, not an automated integration suite.

## Related services and licence

See [Haku Control System](https://github.com/S3942721/haku_control_system) for orchestration, [Robot Web Controller](https://github.com/S3942721/robo-web-controller) for commands and UI, and [Haku STT](https://github.com/S3942721/haku_stt) for remote recognition.

The repository includes [MIT licence terms](LICENSE.md) with the original attribution. NAOqi, robot behaviours, media, and external models/services retain their own terms.

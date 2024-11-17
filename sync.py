import os
import sys
import subprocess

# Constants
DEFAULT_IP = "192.168.1.100"
REMOTE_USER = "nao"
REMOTE_FOLDER = "/home/nao/pepperchat"
LOCAL_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
HTML_FILE = os.path.join(os.path.dirname(LOCAL_FOLDER), "chatbot.html")
HTML_REMOTE_PATH = "~/.local/share/PackageManager/apps/rmit-race/html/chatbot.html"
PASSWORD_FILE = os.path.join(os.path.dirname(LOCAL_FOLDER), ".pepper_password")
REMOTE_JSON_FILE = "pepperchat/behaviours/behaviours_described.json"
LOCAL_JSON_FILE = os.path.join(LOCAL_FOLDER, "robot_behaviours_described.json")
REMOTE_EXPLORER_FOLDER = "~/.local/share/Explorer"
LOCAL_EXPLORER_FOLDER = os.path.join(os.path.dirname(LOCAL_FOLDER), "explorer")

def run_command(command):
    """Run a shell command and print it."""
    print(f"Running command: {command}")
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        sys.exit(result.returncode)
    print(result.stdout)

def sync_files(remote_ip):
    print("Syncing remote files.")
    print()
    try:
        # Copy the behaviours_described.json file from the remote system to the local system
        check_file_command = f"sshpass -f {PASSWORD_FILE} ssh {REMOTE_USER}@{remote_ip} 'test -f {REMOTE_JSON_FILE}'"
        result = subprocess.run(check_file_command, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            json_copy_command = f"sshpass -f {PASSWORD_FILE} scp {REMOTE_USER}@{remote_ip}:{REMOTE_JSON_FILE} {LOCAL_JSON_FILE}"
            run_command(json_copy_command)
        else:
            print(f"Warning: {REMOTE_JSON_FILE} does not exist on the remote system.")
    except Exception as e:
        print(f"Failed to copy JSON file: {e}")

    try:
        """Sync local files to the remote system."""
        # Remove the existing folder on the remote system
        remove_command = f"sshpass -f {PASSWORD_FILE} ssh {REMOTE_USER}@{remote_ip} 'rm -rf {REMOTE_FOLDER}'"
        run_command(remove_command)
    except Exception as e:
        print(f"Failed to remove remote folder: {e}")

    try:
        # Copy the local folder to the remote system
        copy_command = f"sshpass -f {PASSWORD_FILE} scp -r {LOCAL_FOLDER}/. {REMOTE_USER}@{remote_ip}:{REMOTE_FOLDER}"
        run_command(copy_command)
    except Exception as e:
        print(f"Failed to copy local folder to remote system: {e}")

    try:
        # Copy the chatbot.html file to the remote system
        html_copy_command = f"sshpass -f {PASSWORD_FILE} scp {HTML_FILE} {REMOTE_USER}@{remote_ip}:{HTML_REMOTE_PATH}"
        run_command(html_copy_command)
    except Exception as e:
        print(f"Failed to copy HTML file: {e}")

    try:
        # Copy the contents of the remote Explorer folder to the local explorer folder
        explorer_copy_command = f"sshpass -f {PASSWORD_FILE} scp -r {REMOTE_USER}@{remote_ip}:{REMOTE_EXPLORER_FOLDER}/. {LOCAL_EXPLORER_FOLDER}"
        run_command(explorer_copy_command)
    except Exception as e:
        print(f"Failed to copy Explorer folder: {e}")

def main():
    """Main function to handle command line arguments and initiate file sync."""
    if len(sys.argv) > 1:
        remote_ip = sys.argv[1]
    else:
        remote_ip = DEFAULT_IP

    print(f"Using remote IP: {remote_ip}")
    sync_files(remote_ip)

if __name__ == "__main__":
    main()
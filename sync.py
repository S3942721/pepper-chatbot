import os
import sys
import subprocess
import glob

# Constants
DEFAULT_IP = "192.168.1.100"
REMOTE_USER = "nao"
REMOTE_FOLDER = "/home/nao/pepperchat"
LOCAL_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
HTML_FILES = glob.glob(os.path.join(os.path.dirname(LOCAL_FOLDER), "*.html"))
HTML_REMOTE_PATH = "~/.local/share/PackageManager/apps/rmit-race/html"
PASSWORD_FILE = os.path.join(os.path.dirname(LOCAL_FOLDER), ".pepper_password")
REMOTE_JSON_FILE = "pepperchat/behaviours/behaviours_described.json"
LOCAL_JSON_FILE = os.path.join(LOCAL_FOLDER, "robot_behaviours_described.json")
REMOTE_EXPLORER_FOLDER = "~/.local/share/Explorer"
LOCAL_EXPLORER_FOLDER = os.path.join(os.path.dirname(LOCAL_FOLDER), "explorer")
LOCAL_MEDIA_FOLDER = os.path.join(os.path.dirname(LOCAL_FOLDER), "src/media")
REMOTE_MEDIA_FOLDER = os.path.join(REMOTE_FOLDER, "media")

def run_command(command):
    """Run a shell command and print it."""
    print(f"Running command: {command}")
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        sys.exit(result.returncode)
    print(result.stdout)

def sync_files(remote_ip, sync_html):
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

    if sync_html:
        try:
            # Create the remote directory if it does not exist
            create_dir_command = f"sshpass -f {PASSWORD_FILE} ssh {REMOTE_USER}@{remote_ip} 'mkdir -p {HTML_REMOTE_PATH}'"
            run_command(create_dir_command)

            # Copy all .html files to the remote system
            for html_file in HTML_FILES:
                html_copy_command = f"sshpass -f {PASSWORD_FILE} scp {html_file} {REMOTE_USER}@{remote_ip}:{HTML_REMOTE_PATH}"
                run_command(html_copy_command)
        except Exception as e:
            print(f"Failed to copy HTML files: {e}")

    try:
        # Create the remote media directory if it does not exist
        create_media_dir_command = f"sshpass -f {PASSWORD_FILE} ssh {REMOTE_USER}@{remote_ip} 'mkdir -p {REMOTE_MEDIA_FOLDER}'"
        run_command(create_media_dir_command)

        # Copy the local media folder to the remote system
        media_copy_command = f"sshpass -f {PASSWORD_FILE} scp -r {LOCAL_MEDIA_FOLDER}/. {REMOTE_USER}@{remote_ip}:{REMOTE_MEDIA_FOLDER}"
        run_command(media_copy_command)
    except Exception as e:
        print(f"Failed to copy media folder: {e}")

def main():
    """Main function to handle command line arguments and initiate file sync."""
    sync_html = False
    remote_ip = DEFAULT_IP

    for arg in sys.argv[1:]:
        if arg == "-h":
            sync_html = True
        else:
            remote_ip = arg

    print(f"Using remote IP: {remote_ip}")
    print(f"Sync HTML: {sync_html}")
    sync_files(remote_ip, sync_html)

if __name__ == "__main__":
    main()
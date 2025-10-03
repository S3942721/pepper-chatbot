from naoqi import ALProxy, ALBroker
import os
import sys
import time
from optparse import OptionParser
import random

def main():
    parser = OptionParser()
    parser.add_option("--ip",
        help="Robot IP address",
        dest="ip",
        default="localhost")
    parser.add_option("--port",
        help="NAOqi port",
        dest="port",
        type="int",
        default=9559)
    parser.add_option("--folder",
        help="Folder path to save image",
        dest="folder",
        default="/home/nao/images")
    parser.add_option("--filename",
        help="Image filename",
        dest="filename", 
        default="image.jpg")
    
    opts = parser.parse_args()[0]
    
    # Setup broker
    myBroker = ALBroker("myBroker",
       "0.0.0.0",
       0,
       opts.ip,
       opts.port
    )
    
    try:
        # Create photo capture proxy
        photo_capture = ALProxy("ALPhotoCapture", opts.ip, opts.port)
        
        # Configure camera settings
        photo_capture.setCameraID(0)  # Top camera
        photo_capture.setResolution(2)  # VGA (640x480)
        photo_capture.setPictureFormat("jpg")
        photo_capture.setColorSpace(13)  # BGR color space

        while (True):
            filename = "image_" + str(int(time.time())) + ".jpg"
            
            # Take picture
            print("Taking picture...")
            result = photo_capture.takePicture(opts.folder, filename)
            print("Picture saved:", result)
            time.sleep(random.randint(5, 15))  # Wait between 5 to 15 seconds before next capture
        
    except Exception as e:
        print("Error:", e)
    finally:
        myBroker.shutdown()

if __name__ == "__main__":
    main()

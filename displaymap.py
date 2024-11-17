#! /usr/bin/env python3
# -*- encoding: UTF-8 -*-

"""Example: Use explore method in Python 3."""

import qi
import argparse
import sys
import numpy as np
import matplotlib.pyplot as plt

def main(session):
    """
    This example uses the explore method.
    """
    # Get the services ALNavigation and ALMotion.
    navigation_service = session.service("ALNavigation")
    motion_service = session.service("ALMotion")

    # Wake up robot
    motion_service.wakeUp()

    # Explore the environment in a radius of 2 m.
    radius = 2.0
    error_code = navigation_service.explore(radius)
    if error_code != 0:
        print("Exploration failed.")
        return

    # Save the exploration on disk
    path = navigation_service.saveExploration()
    print(f"Exploration saved at path: \"{path}\"")

    # Start localization to navigate in the map
    navigation_service.startLocalization()
    # Come back to initial position
    navigation_service.navigateToInMap([0.0, 0.0, 0.0])
    # Stop localization
    navigation_service.stopLocalization()

    # Retrieve and display the map built by the robot
    result_map = navigation_service.getMetricalMap()
    map_width = result_map[1]
    map_height = result_map[2]
    img_data = np.array(result_map[4]).reshape((map_width, map_height))
    img_data = (100 - img_data) * 2.55  # Convert from 0..100 to 255..0
    img_data = img_data.astype(np.uint8)

    # Display the image using matplotlib
    plt.imshow(img_data, cmap='gray', origin='lower')
    plt.title("Robot Metrical Map")
    plt.colorbar(label='Occupancy Probability')
    plt.show()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", type=str, default="192.168.1.100",
                        help="Robot IP address. On robot or Local Naoqi: use

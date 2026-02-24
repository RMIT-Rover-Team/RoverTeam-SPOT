# kinematics/ik.py
import os

import numpy as np
from ikpy.chain import Chain
from ikpy.link import OriginLink
from math import radians
from typing import List, Tuple

# Load the URDF
CHAIN = Chain.from_urdf_file(os.path.join(os.path.dirname(__file__), "arm.urdf"))

# IKPy expects target as 4x4 transformation matrix
def rpy_to_matrix(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """Convert roll, pitch, yaw (degrees) to 4x4 rotation matrix"""
    roll = radians(roll)
    pitch = radians(pitch)
    yaw = radians(yaw)

    Rx = np.array([
        [1, 0, 0, 0],
        [0, np.cos(roll), -np.sin(roll), 0],
        [0, np.sin(roll), np.cos(roll), 0],
        [0, 0, 0, 1]
    ])

    Ry = np.array([
        [np.cos(pitch), 0, np.sin(pitch), 0],
        [0, 1, 0, 0],
        [-np.sin(pitch), 0, np.cos(pitch), 0],
        [0, 0, 0, 1]
    ])

    Rz = np.array([
        [np.cos(yaw), -np.sin(yaw), 0, 0],
        [np.sin(yaw), np.cos(yaw), 0, 0],
        [0, 0, 1, 0],
        [0, 0, 0, 1]
    ])

    return Rz @ Ry @ Rx

def pose_to_matrix(x: float, y: float, z: float, roll: float, pitch: float, yaw: float) -> np.ndarray:
    """Build a 4x4 transformation matrix from xyz and RPY"""
    mat = rpy_to_matrix(roll, pitch, yaw)
    mat[0, 3] = x / 1000  # convert mm to meters if URDF is in meters
    mat[1, 3] = y / 1000
    mat[2, 3] = z / 1000
    return mat

def solve_ik(x: float, y: float, z: float, roll: float, pitch: float, yaw: float) -> List[float]:
    """
    Solve IK for the arm.

    Returns a list of 6 joint angles in degrees [J1..J6]
    """
    target_matrix = pose_to_matrix(x, y, z, roll, pitch, yaw)

    # Compute IK solution
    joint_angles_rad = CHAIN.inverse_kinematics(target_matrix)

    # IKPy returns angles including the fixed origin link, so skip it
    # Also only take the first 6 joints corresponding to J1..J6
    joint_angles_deg = [np.degrees(a) for a in joint_angles_rad[1:7]]
    return joint_angles_deg
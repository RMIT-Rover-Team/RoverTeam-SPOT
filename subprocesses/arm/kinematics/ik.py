# kinematics/ik.py
import os
import numpy as np
from ikpy.chain import Chain
from math import radians, degrees
from typing import List

# -------------------------
# Load the URDF chain
# -------------------------
URDF_PATH = os.path.join(os.path.dirname(__file__), "arm.urdf")
CHAIN = Chain.from_urdf_file(URDF_PATH)

# -------------------------
# Helpers: RPY to 4x4 matrix
# -------------------------
def rpy_to_matrix(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """Convert roll, pitch, yaw (degrees) to 4x4 rotation matrix."""
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
    """
    Build a 4x4 transformation matrix from position (mm) and RPY (degrees).
    Converts mm -> meters for URDF.
    """
    mat = rpy_to_matrix(roll, pitch, yaw)
    mat[0, 3] = x / 1000.0
    mat[1, 3] = y / 1000.0
    mat[2, 3] = z / 1000.0
    return mat

# -------------------------
# IK Solver
# -------------------------
def solve_ik(x: float, y: float, z: float, roll: float, pitch: float, yaw: float) -> List[float]:
    """
    Solve IK for the arm.

    Returns a list of 6 joint angles in degrees [J1..J6]
    """
    target_frame = pose_to_matrix(x, y, z, roll, pitch, yaw)

    # Length of active_links_mask for initial position
    n_joints = len(CHAIN.active_links_mask)

    # Call inverse_kinematics positionally (do NOT use 'target=' keyword)
    joint_angles_rad = CHAIN.inverse_kinematics(
        target_frame,
        initial_position=[0.0] * n_joints
    )

    # Skip fixed base link, take first 6 active joints
    joint_angles_deg = [np.degrees(a) for a in joint_angles_rad[1:7]]
    return joint_angles_deg
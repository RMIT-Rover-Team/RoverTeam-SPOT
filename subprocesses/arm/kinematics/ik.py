# kinematics/ik.py
import os
from math import radians
from typing import List

import numpy as np
from ikpy.chain import Chain

# -------------------------
# Load URDF
# -------------------------
CHAIN = Chain.from_urdf_file(
    os.path.join(os.path.dirname(__file__), "arm.urdf"),
    base_elements=["base_link"],
    last_link_vector=[0, 0, 0.02]
)

# -------------------------
# Utility: RPY -> 4x4 rotation
# -------------------------
def rpy_to_matrix(roll: float, pitch: float, yaw: float) -> np.ndarray:
    r, p, y = map(radians, (roll, pitch, yaw))
    Rx = np.array([[1,0,0,0],[0,np.cos(r),-np.sin(r),0],[0,np.sin(r),np.cos(r),0],[0,0,0,1]])
    Ry = np.array([[np.cos(p),0,np.sin(p),0],[0,1,0,0],[-np.sin(p),0,np.cos(p),0],[0,0,0,1]])
    Rz = np.array([[np.cos(y),-np.sin(y),0,0],[np.sin(y),np.cos(y),0,0],[0,0,1,0],[0,0,0,1]])
    return Rz @ Ry @ Rx

# -------------------------
# Pose -> 4x4 matrix
# -------------------------
def pose_to_matrix(x: float, y: float, z: float, roll: float, pitch: float, yaw: float) -> np.ndarray:
    mat = rpy_to_matrix(roll, pitch, yaw)
    mat[0, 3] = x / 1000  # mm -> m
    mat[1, 3] = y / 1000
    mat[2, 3] = z / 1000
    return mat

# -------------------------
# Solve IK
# -------------------------
def solve_ik(x: float, y: float, z: float, roll: float, pitch: float, yaw: float) -> List[float]:
    target_frame = pose_to_matrix(x, y, z, roll, pitch, yaw)
    n_joints = len(CHAIN.links)

    # Use IKPy full-frame solver
    joint_angles_rad = CHAIN.inverse_kinematics_frame(
        target_frame,
        initial_position=[0.0] * n_joints,
        max_iter=100
    )

    # Only the 6 active joints (skip base/fixed links)
    joint_angles_deg = [np.degrees(a) for a in joint_angles_rad[1:7]]
    return joint_angles_deg
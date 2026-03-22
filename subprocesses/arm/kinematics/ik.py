import math
import numpy as np

def solve_ik(joints, links, target):

    # J1 Implementation
    j1 = joints[0]
    dx = target[0]
    dy = target[1]
    angle_rad = math.atan2(dy, dx)
    angle_deg = math.degrees(angle_rad)
    j1.set_angle(angle_deg)

    # J2/J3 Implementation
    target_vec = np.array([dx, dy, 0])
    distance_xy = np.linalg.norm(target_vec)

    # Correct for L1 vertical link height
    z = -(target[2] - links['L1'].length)
    x = distance_xy  # forward along J1 direction

    # Planar (2D) 2-link IK
    l1 = links['L2'].length
    l2 = links['L3'].length

    # Clamp distance
    r = math.hypot(x, z)
    r = max(min(r, l1 + l2), abs(l1 - l2))

    cos_angle2 = (x**2 + z**2 - l1**2 - l2**2) / (2 * l1 * l2)
    cos_angle2 = np.clip(cos_angle2, -1.0, 1.0)
    theta2 = math.atan2(math.sqrt(1 - cos_angle2**2), cos_angle2)  # solve for elbow-up

    theta1 = math.atan2(z, x) - math.atan2(l2 * math.sin(theta2), l1 + l2 * math.cos(theta2))

    # Convert to degrees
    joints[1].set_angle(math.degrees(theta1))
    joints[2].set_angle(math.degrees(theta2))
import numpy as np
import math
from sympy import symbols, Matrix, sin, cos, atan2, sqrt, pi


class RobotArm6DOF:

    def __init__(
        self,
        d1,
        a1,
        a2,
        a3,
        d4,
        d7,
        alpha_vals=None,
        joint_directions=None
    ):
        """
        Define full robot geometry here.

        All units in meters.
        All angles in radians.
        """

        # ---- Link dimensions ----
        self.d1 = d1
        self.a1 = a1
        self.a2 = a2
        self.a3 = a3
        self.d4 = d4
        self.d7 = d7

        # Derived triangle geometry
        self.l = math.sqrt(d4**2 + a3**2)
        self.phi = math.atan2(d4, abs(a3)) if a3 != 0 else math.pi/2

        # ---- DH twist angles ----
        # Default matches your original model
        if alpha_vals is None:
            self.alpha_vals = [
                0,
                -math.pi/2,
                0,
                -math.pi/2,
                math.pi/2,
                -math.pi/2
            ]
        else:
            self.alpha_vals = alpha_vals

        # ---- Joint direction flips ----
        # Use -1 if a motor is mounted reversed
        if joint_directions is None:
            self.joint_directions = [1, 1, 1, 1, 1, 1]
        else:
            self.joint_directions = joint_directions

    # ======================================================
    # DH Transform
    # ======================================================

    def pose(self, theta, alpha, a, d):
        return Matrix([
            [cos(theta), -sin(theta), 0, a],
            [sin(theta)*cos(alpha), cos(theta)*cos(alpha), -sin(alpha), -d*sin(alpha)],
            [sin(theta)*sin(alpha), cos(theta)*sin(alpha),  cos(alpha),  d*cos(alpha)],
            [0, 0, 0, 1]
        ])

    # ======================================================
    # Forward Kinematics
    # ======================================================

    def forward_kin(self, q):

        q = [q[i] * self.joint_directions[i] for i in range(6)]
        d90 = pi/2

        T01 = self.pose(q[0], self.alpha_vals[0], 0, self.d1)
        T12 = self.pose(q[1] - d90, self.alpha_vals[1], self.a1, 0)
        T23 = self.pose(q[2], self.alpha_vals[2], self.a2, 0)
        T34 = self.pose(q[3], self.alpha_vals[3], self.a3, self.d4)
        T45 = self.pose(q[4], self.alpha_vals[4], 0, 0)
        T56 = self.pose(q[5], self.alpha_vals[5], 0, 0)
        T6g = self.pose(0, 0, 0, self.d7)

        T = T01 * T12 * T23 * T34 * T45 * T56 * T6g

        px = float(T[0, 3])
        py = float(T[1, 3])
        pz = float(T[2, 3])

        R = np.array(T[:3, :3]).astype(np.float64)

        return px, py, pz, R

    # ======================================================
    # Inverse Kinematics
    # ======================================================

    def inverse_kin(self, x, y, z, roll, pitch, yaw):
        """
        Compute inverse kinematics for the desired end-effector pose.

        Returns:
            q: List of 6 joint angles in radians (after direction flips)
            success: bool, True if target reachable, False if clamped
            achievable_pos: tuple (x, y, z) of actual reachable wrist position
        """
        success = True

        # ---- Rotation matrix from Euler (ZYX) ----
        R_x = np.array([
            [1, 0, 0],
            [0, math.cos(roll), -math.sin(roll)],
            [0, math.sin(roll), math.cos(roll)]
        ])

        R_y = np.array([
            [math.cos(pitch), 0, math.sin(pitch)],
            [0, 1, 0],
            [-math.sin(pitch), 0, math.cos(pitch)]
        ])

        R_z = np.array([
            [math.cos(yaw), -math.sin(yaw), 0],
            [math.sin(yaw),  math.cos(yaw), 0],
            [0, 0, 1]
        ])

        R0g = R_z @ R_y @ R_x

        # ---- Wrist center ----
        nx, ny, nz = R0g[:, 2]
        xw = x - self.d7 * nx
        yw = y - self.d7 * ny
        zw = z - self.d7 * nz

        # ---- Vector from base to wrist ----
        dx = xw
        dy = yw
        dz = zw - self.d1
        dist = math.sqrt(dx**2 + dy**2 + dz**2)
        max_reach = self.a2 + self.l

        # ---- Clamp to reachable workspace ----
        if dist > max_reach:
            success = False
            scale = max_reach / dist
            dx *= scale
            dy *= scale
            dz *= scale
            xw = dx
            yw = dy
            zw = dz + self.d1

        achievable_pos = (xw, yw, zw)

        # ---- First 3 joint angles (planar IK) ----
        r = math.sqrt(xw**2 + yw**2)
        s = zw - self.d1

        def safe_acos(val):
            return math.acos(max(-1.0, min(1.0, val)))

        # Law of cosines
        D = (r**2 + s**2 - self.a2**2 - self.l**2) / (2 * self.a2 * self.l)
        D = max(-1.0, min(1.0, D))
        q3 = math.atan2(-math.sqrt(1 - D**2), D) + self.phi  # elbow-down
        q2 = math.atan2(s, r) - math.atan2(self.l * math.sin(q3 - self.phi), self.a2 + self.l * math.cos(q3 - self.phi))
        q1 = math.atan2(yw, xw)

        # ---- Compute wrist orientation ----
        try:
            R03 = self.forward_kin([q1, q2, q3, 0, 0, 0])[3]
            R36 = R03.T @ R0g
            q4 = math.atan2(R36[2, 2], -R36[0, 2])
            q5 = math.atan2(math.sqrt(R36[0, 2]**2 + R36[2, 2]**2), R36[1, 2])
            q6 = math.atan2(-R36[1, 1], R36[1, 0])
        except Exception:
            success = False
            q4 = q5 = q6 = 0.0

        q = [q1, q2, q3, q4, q5, q6]

        # ---- Apply joint direction flips ----
        q = [q[i] * self.joint_directions[i] for i in range(6)]

        return q, success, achievable_pos
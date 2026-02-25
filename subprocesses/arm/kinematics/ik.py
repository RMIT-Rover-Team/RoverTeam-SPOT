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
        Compute inverse kinematics for the 6DOF arm.

        Args:
            x, y, z: target end-effector position in meters
            roll, pitch, yaw: target orientation in radians

        Returns:
            q: list of 6 joint angles [rad]
            success: bool, True if target reachable
            achievable_pos: tuple (x, y, z) of actual reachable wrist position
        """
        success = True
        epsilon = 1e-3  # 1 mm tolerance

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

        print(f"[IK DEBUG] Wrist center before clamping: x={xw:.3f}, y={yw:.3f}, z={zw:.3f}")

        # ---- Distance in plane for first 3 joints ----
        x_prime = math.sqrt(xw**2 + yw**2)
        mx = x_prime - self.a1
        my = zw - self.d1
        m = math.sqrt(mx**2 + my**2)

        max_reach = self.a2 + self.l

        # ---- Only clamp if truly unreachable ----
        if m > max_reach + epsilon:
            success = False
            # scale down vector to max reach
            scale = max_reach / m
            mx *= scale
            my *= scale
            # update wrist position (clamped)
            xw_clamped = (mx + self.a1) * (xw / x_prime) if x_prime != 0 else 0.0
            yw_clamped = (mx + self.a1) * (yw / x_prime) if x_prime != 0 else 0.0
            zw_clamped = my + self.d1
            print(f"[IK DEBUG] Target unreachable, clamping wrist to: x={xw_clamped:.3f}, y={yw_clamped:.3f}, z={zw_clamped:.3f}")
            xw, yw, zw = xw_clamped, yw_clamped, zw_clamped
        achievable_pos = (xw, yw, zw)

        # ---- Helper for safe acos ----
        def safe_acos(val):
            return math.acos(max(-1.0, min(1.0, val)))

        # ---- First 3 joint angles ----
        alpha = math.atan2(my, mx)
        gamma = safe_acos((self.l**2 + self.a2**2 - m**2) / (2*self.l*self.a2))
        beta  = safe_acos((m**2 + self.a2**2 - self.l**2) / (2*m*self.a2))

        q1 = math.atan2(yw, xw)
        q2 = math.pi/2 - beta - alpha
        q3 = -(gamma - self.phi)

        print(f"[IK DEBUG] q1={math.degrees(q1):.1f}, q2={math.degrees(q2):.1f}, q3={math.degrees(q3):.1f}")

        # ---- Compute wrist orientation ----
        try:
            R03 = self.forward_kin([q1, q2, q3, 0, 0, 0])[3]
            R36 = R03.T @ R0g
            q4 = math.atan2(R36[2, 2], -R36[0, 2])
            q5 = math.atan2(math.sqrt(R36[0, 2]**2 + R36[2, 2]**2), R36[1, 2])
            q6 = math.atan2(-R36[1, 1], R36[1, 0])
        except Exception:
            # fallback if orientation is unreachable
            success = False
            q4 = q5 = q6 = 0.0

        q = [q1, q2, q3, q4, q5, q6]

        # ---- Apply joint direction flips ----
        q = [q[i] * self.joint_directions[i] for i in range(6)]

        return q, success, achievable_pos
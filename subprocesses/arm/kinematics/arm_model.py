import numpy as np
import math


# ===============================
# Joint
# ===============================

class Joint:
    def __init__(self, config):
        self.name = config["name"]
        self.axis = np.array(config["axis"], dtype=float)
        self.limits = config["limits"]
        self.home = config.get("home", 0)
        self.stow = config.get("stow", 0)
        self.gearing = config.get("gearing", 1)

        self.link_from = config.get("linkFrom", None)
        self.link_to = config.get("linkTo", None)

        self.angle_deg = self.home  # current joint position

    def set_angle(self, angle_deg):
        self.angle_deg = max(self.limits[0], min(self.limits[1], angle_deg))


# ===============================
# Link
# ===============================

class Link:
    def __init__(self, config):
        self.name = config["name"]
        self.length = config["length"]
        self.vector = config.get("vector", [1, 0, 0])  # default along X

# ===============================
# Arm Model
# ===============================

class ArmModel:
    def __init__(self, joints, links):
        self.joints = joints
        self.links = {link.name: link for link in links}

        self.base_joint = self._find_base_joint()
        self.end_effector_link = self._find_end_effector_link()

    def update(self, dt, update_fn=None):
        """
        Updates the arm state for this frame.
        
        Args:
            dt: float, seconds since last frame
            update_fn: function(joints, dt) -> modifies joint angles
        """
        if update_fn is not None:
            update_fn(self.joints, self.links, dt)

    # ---------------------------
    # Auto-detect base joint
    # ---------------------------

    def _find_base_joint(self):
        for joint in self.joints:
            if joint.link_from is None:
                return joint
        raise Exception("No base joint found")

    # ---------------------------
    # Auto-detect end effector
    # ---------------------------

    def _find_end_effector_link(self):
        link_from_set = set()
        for joint in self.joints:
            if joint.link_from:
                link_from_set.add(joint.link_from)

        link_names = set(self.links.keys())
        end_links = link_names - link_from_set

        if len(end_links) != 1:
            raise Exception("Cannot uniquely determine end effector")

        return list(end_links)[0]

    # ---------------------------
    # Forward Kinematics
    # ---------------------------

    def compute_joint_positions_and_matrices(self):
        """
        Returns:
            positions: list of np.array([x,y,z]) of each joint + end effector
            transforms: list of 4x4 np.array of world transforms for each joint
        Uses:
            X → forward
            Y → left
            Z → up
        """
        positions = []
        transforms = []
        T = np.eye(4)  # base transform

        for joint in self.joints:
            # Save current joint position
            positions.append(T[:3, 3].copy())
            transforms.append(T.copy())

            # --- Apply joint rotation ---
            angle_rad = math.radians(joint.angle_deg)
            R = self._rotation_matrix(joint.axis, angle_rad)
            T = T @ R

            # --- Apply link translation ---
            if joint.link_to:
                link = self.links[joint.link_to]
                # Use vector if defined, else default along X
                link_vector = getattr(link, "vector", [1, 0, 0])
                translation_vec = np.array(link_vector) * link.length
                T = T @ self._translation_matrix(translation_vec)

        # Add end effector as extra "joint" (no rotation, just translation)
        positions.append(T[:3, 3].copy())
        transforms.append(T.copy())

        return positions, transforms

    # ---------------------------
    # Matrix helpers
    # ---------------------------

    def _rotation_matrix(self, axis, angle):
        axis = axis / np.linalg.norm(axis)
        x, y, z = axis
        c = math.cos(angle)
        s = math.sin(angle)
        C = 1 - c

        R = np.array([
            [x*x*C + c,   x*y*C - z*s, x*z*C + y*s, 0],
            [y*x*C + z*s, y*y*C + c,   y*z*C - x*s, 0],
            [z*x*C - y*s, z*y*C + x*s, z*z*C + c,   0],
            [0, 0, 0, 1]
        ])

        return R

    def _translation_matrix(self, vec):
        T = np.eye(4)
        T[:3, 3] = vec
        return T
# kinematics/differential_velocity.py

class DifferentialVelocityController:
    """
    Differential velocity controller.

    - Input: commanded velocity (deg/s)
    - Integrates into target position (deg)
    - Outputs bounded velocity command toward that position
    - No PID (motor handles low-level loop)
    """

    def __init__(self, max_speed_deg_s: float = 10.0):
        self.max_speed = abs(max_speed_deg_s)
        self.target_position = 0.0
        self._initialised = False

    def update(
        self,
        measured_position: float,
        commanded_velocity: float,
        dt: float,
    ) -> float:
        """
        Returns velocity command (deg/s)
        """

        # Initialise target to current position on first run
        if not self._initialised:
            self.target_position = measured_position
            self._initialised = True

        # Integrate commanded velocity into target position
        self.target_position += commanded_velocity * dt

        # Position error
        error = self.target_position - measured_position

        # Convert position error into velocity
        # (pure proportional, gain = 1)
        velocity_cmd = error

        # Clamp velocity
        if velocity_cmd > self.max_speed:
            velocity_cmd = self.max_speed
        elif velocity_cmd < -self.max_speed:
            velocity_cmd = -self.max_speed

        return velocity_cmd

    def reset(self):
        self._initialised = False
        self.target_position = 0.0
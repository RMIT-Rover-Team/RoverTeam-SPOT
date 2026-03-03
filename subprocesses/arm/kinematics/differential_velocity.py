# kinematics/differential_velocity.py

class DifferentialVelocityController:
    """
    Differential position controller.

    velocity_cmd = clamp(target_position - measured_position)

    No PID.
    No gain.
    Pure position difference limited by max speed.
    """

    def __init__(self, max_speed_deg_s: float = 10.0):
        self.max_speed = abs(max_speed_deg_s)
        self.target_position = 0.0
        self._initialised = False

    def update(self, measured_position, commanded_velocity, dt):

        # Initialise target on first run
        if not self._initialised:
            self.target_position = measured_position
            self._initialised = True

        # Integrate commanded velocity into target position
        self.target_position += commanded_velocity * dt

        # Position difference
        velocity_cmd = self.target_position - measured_position

        # Clamp to max velocity
        if velocity_cmd > self.max_speed:
            velocity_cmd = self.max_speed
        elif velocity_cmd < -self.max_speed:
            velocity_cmd = -self.max_speed

        return velocity_cmd

    def reset(self):
        self._initialised = False
        self.target_position = 0.0
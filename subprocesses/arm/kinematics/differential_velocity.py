class DifferentialVelocityController:
    """
    Binary differential controller.

    Moves at ±max_speed toward target.
    Stops inside tolerance band.
    """

    def __init__(self, max_speed_deg_s: float = 10.0, tolerance_deg: float = 0.2):
        self.max_speed = abs(max_speed_deg_s)
        self.tolerance = abs(tolerance_deg)
        self.target_position = 0.0
        self._initialised = False

    def update(self, measured_position, commanded_velocity, dt):

        if not self._initialised:
            self.target_position = measured_position
            self._initialised = True

        # Integrate joystick velocity into target
        self.target_position += commanded_velocity * dt

        error = self.target_position - measured_position

        if error > self.tolerance:
            return self.max_speed
        elif error < -self.tolerance:
            return -self.max_speed
        else:
            return 0.0

    def reset(self):
        self._initialised = False
        self.target_position = 0.0
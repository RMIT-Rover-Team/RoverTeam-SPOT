def closest_equivalent_angle(target_deg: float, current_deg: float) -> float:
    """
    Returns the equivalent target angle (adding ±360k)
    that is closest to current angle.
    """
    diff = target_deg - current_deg
    diff = (diff + 180) % 360 - 180
    return current_deg + diff

def shortest_angle_delta(current_deg: float, target_deg: float) -> float:
    """
    Compute shortest delta from current to target for multi-turn degrees.

    Returns a signed delta in degrees, taking the shortest path.
    """
    delta = (target_deg - current_deg) % 360.0  # wrap into [0, 360)
    if delta > 180.0:
        delta -= 360.0  # wrap into [-180, 180]
    return delta

def clamp(x, minimum, maximum):
    return max(min(x, maximum), minimum)

def closest_multi_turn_target(current_pos_deg: float, target_deg: float) -> float:
    """
    Given a current multi-turn position and a desired single-turn angle,
    return the closest equivalent multi-turn target.
    """
    delta = shortest_angle_delta(current_pos_deg, target_deg)
    return current_pos_deg + delta
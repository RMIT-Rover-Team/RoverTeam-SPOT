def closest_equivalent_angle(target_deg: float, current_deg: float) -> float:
    """
    Returns the equivalent target angle (adding ±360k)
    that is closest to current angle.
    """
    diff = target_deg - current_deg
    diff = (diff + 180) % 360 - 180
    return current_deg + diff
import json5
from .arm_model import Joint, Link, ArmModel


def load_arm_from_file(path):
    with open(path, "r") as f:
        data = json5.load(f)

    joints = [Joint(j) for j in data["joints"]]
    links = [Link(l) for l in data["links"]]

    return ArmModel(joints, links)
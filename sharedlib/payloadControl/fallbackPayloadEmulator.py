class PyRover:
    def __init__(self, canbus, masterID):
        print("IMPORT FAIL EMULATING PAYLOAD")
        pass

    def EStop(self,ID):
        print("EStop payload")

    def ping(self,ID):
        return True
    
    def Calibrate(self,ID: int, motorID: int):
        print("Calibrate motor " + str(motorID))
        return True
    
    def SetMotorSpeed(self,ID: int, motorID: int, speed: float):
        print("Set motor speed " + str(speed) + " for motor " + str(motorID))
        return {}
    
    def SetMotorPosition(self,ID: int, motorID: int, position: float):
        print("Set motor position " + str(position) + " for motor " + str(motorID))
        return {}
    
    def GetMotorPosition(self,ID: int, motorID: int):
        print("Get motor position for motor " + str(motorID))
        return ({}, 0.123456)
    
    def GetMotorSpeed(self,ID: int, motorID: int):
        print("Get motor speed for motor " + str(motorID))
        return ({}, 0.123456)
    
    def ToggleState(self,ID: int, motorID: int, value: bool):
        print("Toggle motor state " + str(motorID) + " to " + str(value))
        return {}
    
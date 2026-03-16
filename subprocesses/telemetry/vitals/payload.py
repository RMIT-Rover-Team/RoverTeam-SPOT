import sharedlib.utilities.WheresMyPayload as WMP
import threading
import time


LastPayloadStatus = None

def _payloadChecker():
    global LastPayloadStatus
    while True:
        LastPayloadStatus = WMP.findPayload()
        #print(LastPayloadStatus)
        time.sleep(1)


LP = threading.Thread(target=_payloadChecker, name="Payload Checker")
LP.start()


def payloadAlive():
    LastSeen, Status = LastPayloadStatus

    return {
        "lastSeen":LastSeen,
        "Status":Status
    }
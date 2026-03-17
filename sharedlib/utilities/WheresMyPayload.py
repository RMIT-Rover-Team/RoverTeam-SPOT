#Where's my payload?
#Determines if the payload is connected and responding

import time
from sharedlib.payloadControl import pyRover

PayloadID = 0xB
payloadMaster = pyRover.PyRover("can0",0)



PayloadLastSeen = time.time()

#Input: None
#Output: (Last Seen Unix Timestamp, Ping Success Status)
def findPayload() -> tuple[float, bool]:
    global PayloadLastSeen

    if payloadMaster.ping(PayloadID):
        PayloadLastSeen = time.time()
        return PayloadLastSeen, True
    
    return PayloadLastSeen, False

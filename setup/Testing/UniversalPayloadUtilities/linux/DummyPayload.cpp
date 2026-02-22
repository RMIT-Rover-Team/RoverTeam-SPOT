#include <iostream>
#include "../libuniversalcan/RoverCanSlave.h"
#include "../libuniversalcan/SocketCanWrapper.h"

const int PayloadID = 0xB;
const int maxJoints = 8; // Covers Arm and Excavator

//Fake some joints for Excavator and Arm
float jointPositions[maxJoints] = {0};
float jointSpeeds[maxJoints] = {0};

void fakeSetPos(int motor, double value){
    jointPositions[motor] = value;
}

double fakeGetPos(int motor){
    return jointPositions[motor];
}

void fakeSetSpeed(int motor, double value){
    jointSpeeds[motor] = value;
}

double fakeGetSpeed(int motor){
    return jointSpeeds[motor];
}

//Science uses ToggleState (Relays) and getDataPoint
//But the library default examples are already good enough
//So we just leave it be

int main(){
    WrappedCANBus myCan("can0");

    printf("Init Ratcan\n");

    RoverCanSlave mySlave(PayloadID, &myCan);
    printf("Init Slave\n");

    //Add the joint stuff to override default behaviour
    mySlave.handleSetMotorPosition = &fakeSetPos;
    mySlave.handleGetMotorPosition = &fakeGetPos;

    mySlave.handleSetMotorSpeed = &fakeSetSpeed;
    mySlave.handleGetMotorSpeed = &fakeGetSpeed;



    while (true) {
        printf("\nListening....\n");
        mySlave.listen();

        //printf("\nAwaiting next command....\n");
    }
}